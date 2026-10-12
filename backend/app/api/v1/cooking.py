"""烹饪会话路由模块。

职责：
    - POST   /v1/cooking/sessions：创建会话（过敏原冲突检查；阶段一无档案 → 无冲突）；
    - GET    /v1/cooking/sessions/{id}：会话详情（含菜谱步骤快照，断点续做恢复）；
    - PATCH  /v1/cooking/sessions/{id}：步骤推进/断点（action=next|prev|abort、current_step_no、ack）；
    - POST   /v1/cooking/sessions/{id}/finish：完成会话（可选评分，rating 写 recipe_feedback；
               同步写 meal_record 饮食记录，餐次按完成本地时间归集，营养按份数估算）；
    - POST  /v1/cooking/sessions/{id}/help：烹饪求助（优先命中本地关键词库返回针对性常识
               要点（DEF-06），未命中回退当前步骤结构化信息，不调 LLM；
               每会话限 3 次，question 过 RiskEngine input 闸门，回答过 output 闸门）。

    状态机（架构文档 §12.1 五态）：not_started → ongoing → rating → completed；
    abort 保存 abandoned_step_no 并回 not_started（表 CHECK 无 aborted 枚举）；
    非法流转 409、会话不存在 404。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ability.nutrition import estimate_recipe_nutrition
from app.api.v1.deps import (
    ERR_BAD_REQUEST,
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    api_error,
    get_or_create_user,
    resolve_anonymous_id,
)
from app.core.db import get_db
from app.models import CookingHelpLog, CookingSession, MealRecord, Recipe, RecipeFeedback, RecipeStep
from app.safety.engine import RiskVerdict, get_risk_engine
from app.schemas.cooking import (
    CookingSessionCreate,
    CookingSessionPatch,
    FinishRequest,
)

router = APIRouter(prefix="/cooking", tags=["cooking"])

# 每会话求助次数上限（按 cooking_help_log 计数）
_HELP_LIMIT_PER_SESSION = 3
# 限流错误码（deps 现有错误码之外的本域扩展）
ERR_RATE_LIMITED = "RATE_LIMITED"
# output 闸门命中时的兜底回答
_FALLBACK_ANSWER = "这个问题我暂时换个说法：请按菜谱步骤操作，如有具体困难请描述当前现象。"


class CookingHelpRequest(BaseModel):
    """烹饪求助请求体（模型类）。

    说明：
        属烹饪会话域，就近定义于本路由模块（app/schemas/cooking.py 不在本次改动范围）。

    属性：
        question：求助问题（1~500 字）。
        anonymous_id：匿名会话 ID（可缺省，缺省读 X-Anonymous-Id 头或新建匿名用户）。
    """

    question: str = Field(min_length=1, max_length=500)
    anonymous_id: str | None = Field(default=None, max_length=64)


def _session_out(session_row: CookingSession) -> dict:
    """会话 ORM → 响应字典（函数）。

    说明：
        id 字符串化（前端路由 /cook/:sessionId 直接拼接）；
        allergen_conflict 为冲突说明数组（空数组 = 无冲突，前端以 length 判断）；
        allergen_conflict_bool 保留任务口径布尔语义。

    参数：
        session_row：会话 ORM 实例。

    返回值：
        dict：CookingSessionOut 结构。

    异常：
        无。
    """
    conflict_desc: list[str] = []
    if session_row.allergen_conflict and not session_row.allergen_conflict_ack:
        # 冲突未确认时给出固定说明（阶段一冲突恒 false，此分支为档案化预留）
        conflict_desc = ["菜谱含致敏原，与家庭成员过敏原档案冲突，请确认食材标签"]
    return {
        "id": str(session_row.id),
        "recipe_id": int(session_row.recipe_id),
        "servings": int(session_row.servings),
        "current_step_no": int(session_row.current_step_no),
        "status": session_row.status,
        "allergen_conflict": conflict_desc,
        "allergen_conflict_bool": bool(session_row.allergen_conflict),
        "abandoned_step_no": int(session_row.abandoned_step_no) if session_row.abandoned_step_no is not None else None,
        "started_at": session_row.started_at.isoformat() if session_row.started_at else None,
        "completed_at": session_row.completed_at.isoformat() if session_row.completed_at else None,
        "created_at": session_row.created_at.isoformat() if session_row.created_at else None,
    }


def _load_session_or_404(session: Session, session_id: int) -> CookingSession:
    """加载会话或抛 404（函数）。

    参数：
        session：数据库会话。
        session_id：会话主键。

    返回值：
        CookingSession：会话 ORM 实例。

    异常：
        HTTPException 404：会话不存在。
    """
    row = session.execute(
        select(CookingSession).where(CookingSession.id == session_id)
    ).scalar_one_or_none()
    if row is None:
        raise api_error(404, ERR_NOT_FOUND, "烹饪会话不存在", f"session_id={session_id}")
    return row


@router.post("/sessions", summary="创建烹饪会话（过敏原冲突检查）")
def create_cooking_session(
    payload: CookingSessionCreate,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """创建烹饪会话端点（函数）。

    说明：
        - 菜谱须已发布（404）；份数 1~20（Pydantic 校验）；
        - 过敏原冲突检查：阶段一无家庭档案（D8）→ conflict=false 直接 ongoing；
          未来档案化后 conflict=true 时会话停 not_started，需 PATCH ack=true 才进入 ongoing；
        - anonymous_id 解析顺序：请求体 → X-Anonymous-Id 头 → 新建匿名用户。

    参数：
        payload：创建请求体（recipe_id/servings）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        dict：CookingSessionOut 结构（status=ongoing，allergen_conflict=[]）。

    异常：
        HTTPException 404：菜谱不存在；数据库异常向上抛出。
    """
    recipe = session.execute(
        select(Recipe).where(Recipe.id == payload.recipe_id)
    ).scalar_one_or_none()
    if recipe is None or recipe.status != "published":
        raise api_error(404, ERR_NOT_FOUND, "菜谱不存在或未发布", f"recipe_id={payload.recipe_id}")

    anon_id = resolve_anonymous_id(payload.anonymous_id, request)
    user = get_or_create_user(session, anon_id)

    # 过敏原冲突检查（阶段一无档案：用户过敏原集合为空 → 恒无冲突）
    user_allergens: list[str] = []
    conflict_codes = [c for c in user_allergens if c in set(recipe.allergen_codes or []) | set(recipe.ingredient_allergen_codes or [])]
    has_conflict = bool(conflict_codes)

    row = CookingSession(
        user_id=int(user.id),
        recipe_id=int(recipe.id),
        servings=payload.servings,
        current_step_no=1,
        # 冲突时停在 not_started 等待 ack；无冲突直接 ongoing（开始计时）
        status="not_started" if has_conflict else "ongoing",
        allergen_conflict=has_conflict,
        allergen_conflict_ack=not has_conflict,
        started_at=None if has_conflict else datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return _session_out(row)


@router.get("/sessions/{session_id}", summary="会话详情（含菜谱步骤快照，断点续做恢复）")
def get_cooking_session(
    session_id: int,
    session: Session = Depends(get_db),
) -> dict:
    """会话详情端点（函数）。

    说明：
        返回会话实体 + 菜谱步骤快照（前端恢复会话时无需再请求菜谱详情）。

    参数：
        session_id：会话主键。
        session：请求级数据库会话。

    返回值：
        dict：CookingSessionDetailOut 结构（含 recipe_title/total_steps/steps）。

    异常：
        HTTPException 404：会话不存在。
    """
    row = _load_session_or_404(session, session_id)
    recipe = session.execute(
        select(Recipe).where(Recipe.id == row.recipe_id)
    ).scalar_one_or_none()
    steps = session.execute(
        select(RecipeStep).where(RecipeStep.recipe_id == row.recipe_id).order_by(RecipeStep.step_no)
    ).scalars().all()
    body = _session_out(row)
    body.update(
        {
            "recipe_title": recipe.title if recipe else None,
            "total_steps": len(steps),
            "steps": [
                {
                    "no": int(s.step_no),
                    "description": s.description,
                    "duration_sec": int(s.duration_seconds or 0),
                    "tips": s.key_point,
                    "rescue": s.failure_tips,
                    "amount_hint": s.amount_hint,
                    "step_no": int(s.step_no),
                    "duration_seconds": int(s.duration_seconds or 0),
                    "key_point": s.key_point,
                    "failure_tips": s.failure_tips,
                }
                for s in steps
            ],
        }
    )
    return body


@router.patch("/sessions/{session_id}", summary="步骤推进/断点续做（状态机校验）")
def patch_cooking_session(
    session_id: int,
    payload: CookingSessionPatch,
    session: Session = Depends(get_db),
) -> dict:
    """更新烹饪会话端点（函数）。

    说明：
        状态机校验（§12.1）：
        - 仅 ongoing 可推进步骤（current_step_no / next / prev），否则 409；
        - next：最后一步再推进 409；prev：第一步不回退（幂等返回当前态）；
        - abort：ongoing → 保存 abandoned_step_no 并回 not_started（非 ongoing 409）；
        - ack：冲突会话（not_started + allergen_conflict）确认后进入 ongoing；
        - current_step_no 越界（<1 或 >总步数）422。

    参数：
        session_id：会话主键。
        payload：更新请求体（current_step_no / action / ack）。
        session：请求级数据库会话。

    返回值：
        dict：更新后的 CookingSessionOut。

    异常：
        HTTPException 404：会话不存在；409：非法状态流转；422：步骤越界。
    """
    row = _load_session_or_404(session, session_id)
    total_steps = len(
        session.execute(
            select(RecipeStep.id).where(RecipeStep.recipe_id == row.recipe_id)
        ).scalars().all()
    )

    # 过敏原冲突确认：ack=true 且处于 not_started 冲突态 → 进入 ongoing
    if payload.ack and row.status == "not_started" and row.allergen_conflict:
        row.allergen_conflict_ack = True
        row.status = "ongoing"
        if row.started_at is None:
            row.started_at = datetime.now(UTC)

    # abort：放弃做菜（保存断点，回 not_started；此后不可再推进）
    if payload.action == "abort":
        if row.status != "ongoing":
            raise api_error(409, ERR_CONFLICT, f"当前状态 {row.status} 不可放弃", f"status={row.status}")
        row.abandoned_step_no = row.current_step_no
        row.status = "not_started"
        session.commit()
        return _session_out(row)

    # next / prev / current_step_no：仅 ongoing 可推进
    if payload.action in ("next", "prev") or payload.current_step_no is not None:
        if row.status != "ongoing":
            raise api_error(409, ERR_CONFLICT, f"当前状态 {row.status} 不可推进步骤", f"status={row.status}")
        if total_steps <= 0:
            raise api_error(409, ERR_CONFLICT, "菜谱无有效步骤，无法推进", "total_steps=0")

        if payload.current_step_no is not None:
            target = payload.current_step_no
            if target < 1 or target > total_steps:
                raise api_error(422, ERR_BAD_REQUEST, f"步骤序号越界（1~{total_steps}）", f"target={target}")
            row.current_step_no = target
        elif payload.action == "next":
            if row.current_step_no >= total_steps:
                raise api_error(409, ERR_CONFLICT, "已是最后一步，请调用 finish 完成会话", "at_last_step")
            row.current_step_no += 1
        elif payload.action == "prev":
            # 第一步不回退（幂等返回当前态，与前端本地行为一致）
            if row.current_step_no > 1:
                row.current_step_no -= 1

    session.commit()
    return _session_out(row)


def _meal_type_for_local_hour(hour: int) -> str:
    """按本地小时归集餐次（函数）。

    说明：
        5-10 早餐 / 10-14 午餐 / 14-17 加餐 / 17-22 晚餐 / 其余加餐。

    参数：
        hour：本地小时（0~23）。

    返回值：
        str：meal_type（breakfast/lunch/dinner/snack，均为合法枚举值）。

    异常：
        无。
    """
    if 5 <= hour < 10:
        return "breakfast"
    if 10 <= hour < 14:
        return "lunch"
    if 17 <= hour < 22:
        return "dinner"
    return "snack"


def _create_meal_record(session: Session, row: CookingSession) -> MealRecord | None:
    """完成会话时写饮食记录 meal_record（函数）。

    说明：
        - 幂等（upsert 语义）：finish 对重复完成返回 409，故每会话至多产生一条
          source=cooking 记录，此处直接插入即可；
        - 餐次按完成时间本地小时归集（_meal_type_for_local_hour）；
        - 营养复用 ability.nutrition 对该菜谱按会话份数估算（整菜口径）；
        - 🔴 缺失营养不按 0 计：估算结果含 excluded_items（营养数据不完整）时
          整条记录营养字段置空，汇总侧进入「未纳入统计」。

    参数：
        session：请求级数据库会话（estimate 复用同一会话）。
        row：完成中的会话 ORM 实例（status 已置 completed）。

    返回值：
        MealRecord | None：新建记录（已 flush 携带主键）；估算结构异常时返回 None
        （不阻断完成语义）。

    异常：
        不向上抛出（内部兜底为 None，完成流程优先保证）。
    """
    try:
        estimate = estimate_recipe_nutrition(session, int(row.recipe_id), int(row.servings))
        total = estimate.get("total") or {}
        excluded = list(estimate.get("excluded_items") or [])
        completed_local = (row.completed_at or datetime.now(UTC)).astimezone()
        recipe = session.execute(
            select(Recipe).where(Recipe.id == row.recipe_id)
        ).scalar_one_or_none()

        if excluded:
            values: dict[str, float | None] = {
                "kcal": None, "protein_g": None, "fat_g": None, "carbs_g": None, "sodium_mg": None,
            }
        else:
            values = {
                "kcal": round(float(total.get("kcal") or 0.0), 2),
                "protein_g": round(float(total.get("protein_g") or 0.0), 2),
                "fat_g": round(float(total.get("fat_g") or 0.0), 2),
                "carbs_g": round(float(total.get("carbs_g") or 0.0), 2),
                "sodium_mg": round(float(total.get("sodium_mg") or 0.0), 2),
            }
        record = MealRecord(
            user_id=int(row.user_id),
            recorded_date=completed_local.date(),
            meal_type=_meal_type_for_local_hour(completed_local.hour),
            recipe_id=int(row.recipe_id),
            custom_name=recipe.title if recipe else None,
            servings=float(row.servings),
            source="cooking",
            **values,
        )
        session.add(record)
        session.flush()
        return record
    except Exception:  # noqa: BLE001 —— 饮食记录失败不影响完成语义
        return None


def _safety_message(engine, verdict: RiskVerdict) -> str:
    """按风控判定取安全话术（函数）。

    参数：
        engine：RiskEngine 实例。
        verdict：input/output 闸门判定结果。

    返回值：
        str：risk_message 话术正文；无模板时用通用兜底文案。

    异常：
        无（get_message 内部消化数据库异常）。
    """
    message = engine.get_message(verdict.message_id) or {}
    return str(message.get("body") or "该内容涉及安全风险，请调整后再试。")


# ── DEF-06 求助关键词库 ──
# 用途：烹饪求助时按问题关键词返回「可立即执行的通用厨房常识要点」，修复回答与
#       问题无关的缺陷（原实现固定返回当前步骤上下文，答非所问）。
# 维护方式：新增话题时在 _HELP_TOPICS 追加一项 (关键词元组, 要点列表)：
#       - 关键词：2~5 个子串，与既有话题避免重叠（命中按列表序先到先得）；
#       - 要点：固定 2 条，每条一句话、可立即执行、不带品牌/医疗建议；
#       - 回答总长度由端点控制 ≤3 条（第三条并入当前步骤提示），新增话题无需关心。
_HELP_TOPICS: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("太咸", "咸了", "盐多", "盐放多", "齁"),
        [
            "太咸了先加水或没调味的食材同煮几分钟，稀释咸味。",
            "放几块土豆或豆腐一起煮能吸盐，捞出来尝过味再出锅。",
        ],
    ),
    (
        ("太淡", "淡了", "不咸", "没味道", "没味"),
        [
            "少量多次补盐或生抽，每次加完搅匀尝一口再补。",
            "加少许糖或蚝油提鲜，比一次补大量盐更稳。",
        ],
    ),
    (
        ("糊锅", "糊了", "烧糊", "烧焦"),
        [
            "立即关火离灶，把没糊的部分轻轻盛出，别刮糊底。",
            "糊味重就换干净锅续做，糊锅泡水别硬刷。",
        ],
    ),
    (
        ("发苦", "苦了", "苦味"),
        [
            "糖色或酱油炒苦了救不回来，重新起锅小火重炒这一步。",
            "食材本身发苦可加盐抓洗或焯水减轻，出锅前尝味。",
        ],
    ),
    (
        ("没调料", "缺调料", "调料没了", "没有料酒", "没有生抽", "没有盐"),
        [
            "料酒缺了可用姜汁或少量白酒替代，用量减半。",
            "生抽缺了用少许盐加几滴醋和一点糖临时替代。",
        ],
    ),
    (
        ("火候", "大火", "小火", "几成热"),
        [
            "油面轻微波动约五六成热适合爆香，冒大量青烟就是过热了。",
            "拿不准火候就用中小火，宁可慢一点也别烧糊。",
        ],
    ),
    (
        ("溅油", "油溅", "烫到", "烫伤"),
        [
            "烫伤立即用流动凉水冲 15 分钟以上，别涂牙膏或酱油。",
            "起水泡别挑破，皮肤破了或面积大尽快就医。",
        ],
    ),
    (
        ("太辣", "辣了", "辣得很", "辣度"),
        [
            "加点牛奶、酸奶或少许糖，能有效中和辣味。",
            "补些没调味的食材（土豆、豆腐）稀释辣度，盛出多余辣油。",
        ],
    ),
    (
        ("腥味", "去腥", "腥重", "鱼腥"),
        [
            "沿锅边烹一点料酒，或加姜片葱段爆香去腥。",
            "出锅前滴几滴柠檬汁或白醋，也能压住腥味。",
        ],
    ),
    (
        ("粘锅", "粘底", "锅粘", "黏锅"),
        [
            "先离火晾一小会儿再轻晃锅，粘住的食材更容易分离，别急着硬铲。",
            "下一锅记住热锅凉油：锅烧热再倒油润锅，再下食材。",
        ],
    ),
]


def _match_help_topic(question: str) -> list[str] | None:
    """按关键词库匹配求助话题并返回针对性常识要点（函数）。

    说明：
        DEF-06：优先于当前步骤上下文回答，修复「求助答非所问」。
        每类话题固定 2 条要点，第三条由端点并入当前步骤提示（保持总数 ≤3）。
        命中优先级 = _HELP_TOPICS 列表序（先到先得），话题间关键词互不重叠。

    参数：
        question：用户求助问题原文（调用方已 trim）。

    返回值：
        list[str]：命中话题的要点列表（2 条）；未命中返回 None（端点回退步骤要点）。

    异常：
        无。
    """
    if not question:
        return None
    for keywords, points in _HELP_TOPICS:
        if any(k in question for k in keywords):
            return list(points)
    return None


def _build_step_answers(session: Session, row: CookingSession) -> list[str]:
    """按会话当前步骤生成结构化求助回答（函数）。

    说明：
        不调 LLM：当前步骤描述 / 新手要点 / 失败补救（或计时建议），
        共 1~3 条；步骤缺失时返回通用引导。

    参数：
        session：请求级数据库会话。
        row：会话 ORM 实例。

    返回值：
        list[str]：回答列表（1~3 条）。

    异常：
        无。
    """
    step = session.execute(
        select(RecipeStep).where(
            RecipeStep.recipe_id == row.recipe_id,
            RecipeStep.step_no == row.current_step_no,
        )
    ).scalar_one_or_none()
    if step is None:
        return [f"当前进行到第 {int(row.current_step_no)} 步，请按菜谱步骤继续操作，完成后可推进下一步。"]

    answers = [f"当前第 {int(step.step_no)} 步：{step.description}"]
    if step.key_point:
        answers.append(f"要点：{step.key_point}")
    if step.failure_tips:
        answers.append(f"失败补救：{step.failure_tips}")
    elif int(step.duration_seconds or 0) > 0:
        seconds = int(step.duration_seconds)
        answers.append(f"本步建议用时约 {seconds // 60} 分 {seconds % 60} 秒，可让我帮你起计时器。")
    return answers


@router.post("/sessions/{session_id}/help", summary="烹饪求助（当前步骤问答，每会话限 3 次）")
def help_cooking_session(
    session_id: int,
    payload: CookingHelpRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """烹饪求助端点（函数）。

    说明：
        - 会话必须存在且属于本人（否则 404）；
        - 求助次数按 cooking_help_log 按 session_id 计数，≥3 → 429（每次调用均写日志，
          含被风控拦截的调用）；
        - question 过 RiskEngine input 闸门：命中拦截 → 200 {blocked:true,...} 不生成回答；
        - 正常路径优先命中关键词库（_HELP_TOPICS）返回针对性常识要点（2~3 条），
          未命中回退当前步骤结构化信息（首条带「以下是本步要点：」前缀），不调 LLM；
          回答拼接后过 output 闸门，命中即整体替换为兜底话术。

    参数：
        session_id：会话主键。
        payload：求助请求体（question）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        dict：正常 {"blocked": False, "answers": [...]}；
              拦截 {"blocked": True, "rule_id": ..., "message": ..., "answers": []}。

    异常：
        HTTPException 404：会话不存在/非本人；429：求助次数达上限。
    """
    row = _load_session_or_404(session, session_id)
    anon_id = resolve_anonymous_id(payload.anonymous_id, request)
    user = get_or_create_user(session, anon_id)
    session.commit()
    if int(row.user_id) != int(user.id):
        raise api_error(404, ERR_NOT_FOUND, "烹饪会话不存在", f"session_id={session_id}")

    used = int(
        session.execute(
            select(func.count(CookingHelpLog.id)).where(CookingHelpLog.session_id == row.id)
        ).scalar()
        or 0
    )
    if used >= _HELP_LIMIT_PER_SESSION:
        raise api_error(
            429,
            ERR_RATE_LIMITED,
            f"本会话求助次数已达上限（{_HELP_LIMIT_PER_SESSION} 次）",
            f"used={used}",
        )

    engine = get_risk_engine()

    # input 闸门：命中拦截 → 不生成回答，仅留痕
    verdict = engine.scan("input", payload.question)
    if verdict.hit and verdict.block:
        message = _safety_message(engine, verdict)
        session.add(
            CookingHelpLog(
                session_id=int(row.id),
                question=payload.question,
                answer=message,
                risk_hit=True,
                rule_code=verdict.rule_code,
            )
        )
        session.commit()
        return {"blocked": True, "rule_id": verdict.rule_code, "message": message, "answers": []}

    # 结构化回答（DEF-06：优先命中关键词库返回针对性要点；未命中回退当前步骤要点）
    topic_answers = _match_help_topic(payload.question)
    if topic_answers is not None:
        answers = list(topic_answers)
        # 附 1 条当前步骤相关的提示并入第三条（要点/失败补救优先，保持总数 ≤3）
        if len(answers) < 3:
            step_hint = next(
                (a for a in _build_step_answers(session, row) if a.startswith(("要点", "失败补救"))),
                None,
            )
            if step_hint:
                answers.append(step_hint)
    else:
        answers = _build_step_answers(session, row)
        # 回退口径明示：首条加前缀，让用户知道这是步骤要点而非对问题的直接解答
        answers[0] = f"以下是本步要点：{answers[0]}"
    out_verdict = engine.scan("output", " ".join(answers))
    if out_verdict.hit and out_verdict.block:
        answers = [_FALLBACK_ANSWER]

    session.add(
        CookingHelpLog(
            session_id=int(row.id),
            question=payload.question,
            answer="；".join(answers),
            risk_hit=False,
            rule_code=None,
        )
    )
    session.commit()
    return {"blocked": False, "answers": answers}


@router.post("/sessions/{session_id}/finish", summary="完成会话（可选评分，rating 写 recipe_feedback）")
def finish_cooking_session(
    session_id: int,
    payload: FinishRequest | None = None,
    session: Session = Depends(get_db),
) -> dict:
    """完成烹饪会话端点（函数）。

    说明：
        - 仅 ongoing 可完成（409；无评分负载的重复 finish 409）；
        - 幂等评分补录（DEF-05）：会话已完成时携带 rating 的请求不 409，补写
          recipe_feedback(feedback_type='cooked', rating, tags, session_id)，
          每会话至多一条 cooked 评价（重复补录 409「该次烹饪已完成评价」）；
        - status=completed、completed_at=now；
        - rating 非空时写 recipe_feedback(feedback_type='cooked', rating, tags, session_id)；
        - 同步写 meal_record（source=cooking，餐次按完成本地时间归集，营养按份数估算）；
        - 响应附营养小结（复用 estimate_recipe_nutrition，每份口径）与 meal_record_id。

    参数：
        session_id：会话主键。
        payload：完成请求体（rating 1~5 / tags，可整体缺省）。
        session：请求级数据库会话。

    返回值：
        dict：FinishResponse 结构（session + nutrition 小结 + meal_record_id）。

    异常：
        HTTPException 404：会话不存在；409：状态非 ongoing / 重复完成 / 重复评价。
    """
    row = _load_session_or_404(session, session_id)

    # 幂等评分补录（DEF-05）：会话已完成且本次请求显式携带评分 → 补写评价而非 409。
    # 语义边界：无评分负载（rating=None）的重复完成仍 409，finish 幂等语义保持不变；
    # 每会话至多一条 cooked 评价，重复补录 → 409「该次烹饪已完成评价」（前端友好提示）。
    if row.status == "completed" and payload is not None and payload.rating is not None:
        exists = session.execute(
            select(RecipeFeedback.id).where(
                RecipeFeedback.session_id == int(row.id),
                RecipeFeedback.feedback_type == "cooked",
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise api_error(409, ERR_CONFLICT, "该次烹饪已完成评价", "feedback_already_submitted")
        session.add(
            RecipeFeedback(
                user_id=int(row.user_id),
                recipe_id=int(row.recipe_id),
                session_id=int(row.id),
                rating=payload.rating,
                tags=list(payload.tags or []),
                feedback_type="cooked",
            )
        )
        session.commit()
        # 补录不重复写 meal_record / 不重算营养（完成时已落），返回结构对齐正常 finish
        return {"session": _session_out(row), "nutrition": None, "meal_record_id": None}

    if row.status != "ongoing":
        raise api_error(409, ERR_CONFLICT, f"当前状态 {row.status} 不可完成（重复完成）", f"status={row.status}")

    row.status = "completed"
    row.completed_at = datetime.now(UTC)

    body = payload or FinishRequest()
    if body.rating is not None:
        session.add(
            RecipeFeedback(
                user_id=int(row.user_id),
                recipe_id=int(row.recipe_id),
                session_id=int(row.id),
                rating=body.rating,
                tags=list(body.tags or []),
                feedback_type="cooked",
            )
        )
    # 同步写饮食记录（餐次按完成本地时间归集，营养按份数估算；失败不影响完成）
    meal_record = _create_meal_record(session, row)
    session.commit()

    # 营养小结（每份口径；失败降级为 None，不阻断完成）
    nutrition_body = None
    try:
        estimate = estimate_recipe_nutrition(session, int(row.recipe_id), int(row.servings))
        per = estimate.get("per_serving") or {}
        nutrition_body = {
            "kcal": per.get("kcal"),
            "protein": per.get("protein_g"),
            "fat": per.get("fat_g"),
            "carbs": per.get("carbs_g"),
            "sodium": per.get("sodium_mg"),
            "per_serving": int(row.servings),
            "excluded_items": list(estimate.get("excluded_items") or []),
            "estimate_note": estimate.get("estimate_note"),
        }
    except Exception:  # noqa: BLE001 —— 营养小结失败不影响完成语义
        nutrition_body = None

    return {
        "session": _session_out(row),
        "nutrition": nutrition_body,
        "meal_record_id": int(meal_record.id) if meal_record is not None else None,
    }
