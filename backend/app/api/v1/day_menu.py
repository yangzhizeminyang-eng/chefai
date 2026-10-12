"""「今天吃什么」零输入直出推荐路由模块。

职责：
    POST /v1/recommend/day-menu：首页「今天吃什么」入口的零输入推荐——
    用户未选任何食材时，从全量已发布菜谱中直出 ≤6 道「可执行候选」
    （按耗时/难度排序 + 稳定随机扰动，前端按耗时分组展示）。

红线（🔴 任务约束）：
    - 零输入 ≠ 放行态：候选直出前必须经过 hard_filter 布尔硬过滤
      （过敏原 / 忌口 / 难度上限 / 设备，逐维布尔排除），绝不绕过风控；
    - 不改动既有 POST /v1/recommend 主推荐链路（该端点要求 ingredients ≥1，
      走完整 graph 编排 + 幂等缓存；本端点与其互不影响）；
    - 不做幂等缓存：「换一换」由 exclude_ids 区分批次，必须每次出新批。

降级约定（对齐 home.py 惯例）：
    全程 try/except 兜底，任何异常返回空 results + notice，HTTP 恒 200，
    绝不向外抛业务异常。
"""

from __future__ import annotations

import json
import random

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ability.ranking import hard_filter
from app.api.v1.deps import difficulty_label, resolve_existing_user_id, resolve_request_id
from app.core.db import get_db
from app.core.logging import get_logger
from app.graph.runner import load_profile_from_db
from app.models import Recipe, UserSkillProfile
from app.safety import SafetyProfile

router = APIRouter(prefix="/recommend", tags=["推荐"])

logger = get_logger(__name__)

# 单次返回上限（道数）：3~6 道可执行候选
_MAX_RESULTS = 6

# 随机扰动池大小：排序后取前 N 条做一次稳定 shuffle 再取前 6
# （池大于上限时才有扰动空间；同参数请求可重现，不同 exclude_ids 批次有变化）
_SHUFFLE_POOL = 12

# exclude_ids 防御性截断上限（换一换场景批次只增不减，防 SQL IN 列表无限膨胀）
_MAX_EXCLUDE_IDS = 500

# 空结果/降级统一提示文案（引导用户改用「选食材」入口获得更准结果）
_EMPTY_NOTICE = "暂无可推荐的菜谱，去选食材可获得更准的结果"


class DayMenuRequest(BaseModel):
    """零输入推荐请求体（模型类）。

    说明：
        「今天吃什么」无必填字段——空请求体即可获取候选；
        exclude_ids 用于「换一换」翻页：排除上一批 recipe_id 后取新批。

    属性：
        exclude_ids：上一批结果中的 recipe_id 列表（换一换语义；空=首次请求）。
        anonymous_id：匿名会话 ID（可缺省；后端据此加载家庭档案做硬过滤）。
    """

    exclude_ids: list[int] = Field(default_factory=list)
    anonymous_id: str | None = Field(default=None, max_length=64)


def _load_difficulty_cap(session: Session, user_id: int) -> int | None:
    """读取用户难度上限（函数）。

    说明：
        load_profile_from_db 仅合并家庭档案三段与设备清单（不含难度上限），
        难度上限存于 user_skill_profile.difficulty_cap（一人一份）——此处单独
        只读查询，供 hard_filter 难度维度布尔过滤（零输入不放行该维度）。

    参数：
        session：数据库会话。
        user_id：用户数据库 ID。

    返回值：
        int | None：难度上限（1~5）；无档案/查询异常返回 None（难度维度不生效）。

    异常：
        不抛出（查询异常告警后返回 None，不阻断响应）。
    """
    try:
        return session.execute(
            select(UserSkillProfile.difficulty_cap).where(UserSkillProfile.user_id == int(user_id))
        ).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 —— 难度上限读取失败按「未设置」处理
        logger.warning("load difficulty cap failed (user_id=%s): %s", user_id, exc)
        return None


def _normalize_exclude_ids(raw_ids: list[int]) -> list[int]:
    """规整 exclude_ids 为正整数列表（函数）。

    说明：
        逐项显式 int() 转换防注入（非整型条目静默丢弃），去重、去非正值、
        截断至 _MAX_EXCLUDE_IDS（防换一换累积导致 SQL IN 列表膨胀）。

    参数：
        raw_ids：请求体传入的原始 exclude_ids 列表。

    返回值：
        list[int]：规整后的正整数列表（保持首次出现顺序）。

    异常：
        不抛出（任何条目转换失败均丢弃该条目）。
    """
    normalized: list[int] = []
    for raw in raw_ids[:_MAX_EXCLUDE_IDS]:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in normalized:
            normalized.append(value)
    return normalized


def _load_candidates(session: Session, exclude_ids: list[int]) -> list[dict]:
    """查询全量已发布菜谱构造硬过滤候选（函数）。

    说明：
        零输入口径：不按食材召回，直接取 status='published' 的全部菜谱；
        exclude_ids 非空时跳过对应行（换一换）。候选 dict 携带 hard_filter
        所需的 recipe_id/equipment 键及结果展示所需字段（一次查询取全）。

    参数：
        session：数据库会话。
        exclude_ids：需排除的 recipe_id 列表（空=不排除）。

    返回值：
        list[dict]：候选字典列表（recipe_id/title/time_minutes/difficulty/
        calories_kcal/equipment/allergen_codes/ingredient_allergen_codes/
        cover_image_url/source_label）。

    异常：
        异常向上抛出（由端点统一兜底降级）。
    """
    stmt = select(
        Recipe.id,
        Recipe.title,
        Recipe.time_minutes,
        Recipe.difficulty,
        Recipe.calories_kcal,
        Recipe.equipment,
        Recipe.allergen_codes,
        Recipe.ingredient_allergen_codes,
        Recipe.cover_image_url,
        Recipe.source_label,
    ).where(Recipe.status == "published")
    if exclude_ids:
        stmt = stmt.where(Recipe.id.not_in(exclude_ids))
    rows = session.execute(stmt).all()
    return [
        {
            "recipe_id": int(row.id),
            "title": str(row.title or ""),
            "time_minutes": row.time_minutes,
            "difficulty": int(row.difficulty) if row.difficulty is not None else None,
            "calories_kcal": row.calories_kcal,
            "equipment": list(row.equipment or []),
            "allergen_codes": list(row.allergen_codes or []),
            "ingredient_allergen_codes": list(row.ingredient_allergen_codes or []),
            "cover_image_url": row.cover_image_url,
            "source_label": str(row.source_label or ""),
        }
        for row in rows
    ]


def _pick_top_candidates(filtered: list[dict], exclude_ids: list[int]) -> list[dict]:
    """排序 + 稳定随机扰动选取候选（函数）。

    说明：
        先按 (time_minutes or 9999, difficulty, recipe_id) 升序（耗时短的在前），
        取前 _SHUFFLE_POOL 条入池；池大于返回上限时以 str(sorted(exclude_ids))
        为种子做一次随机扰动（同参数请求可重现、不同批次有变化），取前 6 条。

    参数：
        filtered：hard_filter 过滤后保持顺序的候选列表。
        exclude_ids：规整后的排除 ID（作随机种子）。

    返回值：
        list[dict]：最终上桌候选（≤6 条）。

    异常：
        不抛出（排序键取值异常按兜底值参与排序）。
    """
    ordered = sorted(
        filtered,
        key=lambda c: (
            int(c.get("time_minutes") or 9999),
            int(c.get("difficulty") or 0),
            int(c.get("recipe_id") or 0),
        ),
    )
    pool = ordered[:_SHUFFLE_POOL]
    if len(pool) > _MAX_RESULTS:
        rng = random.Random(str(sorted(exclude_ids)))
        rng.shuffle(pool)
    return pool[:_MAX_RESULTS]


def _build_rank_reasons(cand: dict) -> list[str]:
    """构造单条结果的排序理由（函数）。

    说明：
        至少 1 条可解释理由；用语避免绝对化/功效表述（「快手菜，适合今天」
        属场景建议口径，非功效承诺）。

    参数：
        cand：候选字典（消费 time_minutes/difficulty）。

    返回值：
        list[str]：理由文案列表（≥1 条）。

    异常：
        无。
    """
    reasons: list[str] = []
    time_minutes = int(cand.get("time_minutes") or 0)
    if time_minutes > 0:
        reasons.append(f"约 {time_minutes} 分钟即可上桌")
        if time_minutes <= 20:
            reasons.append("快手菜，适合今天")
    if int(cand.get("difficulty") or 0) <= 2:
        reasons.append("步骤简单，容易上手")
    if not reasons:
        reasons.append("今天就可以安排上桌")
    return reasons


@router.post(
    "/day-menu",
    summary="今天吃什么：零输入直出推荐（≤6 道可执行候选，硬过滤不绕过）",
)
def post_day_menu(
    payload: DayMenuRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """零输入直出推荐端点（函数）。

    说明：
        口径：
        - 零输入：请求体无必填食材字段，直接从全量已发布菜谱出候选；
        - 🔴 硬过滤不绕过：构建 SafetyProfile（家庭档案过敏原/忌口/特殊人群 +
          user_skill_profile 设备与难度上限）后必须经过 hard_filter 布尔过滤；
        - ≤6 道：排序 + 稳定随机扰动后取前 6（match_level 固定 can_cook_now，
          零输入无覆盖语义，前端按耗时分组展示，不用该字段）；
        - exclude_ids（换一换）：排除上一批 recipe_id 后取新批；本端点不做
          幂等缓存（每次请求必须出新批，批次由 exclude_ids 区分）；
        - 不改动既有 POST /v1/recommend 主推荐链路。

    参数：
        payload：零输入推荐请求体（exclude_ids/anonymous_id 均可缺省）。
        request：FastAPI 请求对象（request_id/anonymous_id 头解析）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：200 正常体（request_id/safe_mode/results/filtered_by/
        disclaimer_id/trace_id，字段对齐 RecommendResponse；空结果时附加
        notice 引导文案）；异常时降级为空 results + notice，HTTP 恒 200。

    异常：
        全捕获兜底：档案/候选/过滤任一环节失败均返回空 results + notice，
        本端点不向外抛业务异常。
    """
    # request_id：本端点无显式幂等键字段，复用中间件 request_id / 请求头，最后自动生成
    rid = resolve_request_id(None, request)
    body: dict = {
        "request_id": rid,
        "safe_mode": False,
        "results": [],
        "filtered_by": {},
        "disclaimer_id": None,
        "trace_id": None,
    }
    try:
        # 身份：只读解析既有用户（无身份/用户不存在为 None，不创建用户行）
        user_id = resolve_existing_user_id(session, payload.anonymous_id, request)

        # 安全档案：家庭档案三段（过敏原/忌口/特殊人群）+ 本人设备与难度上限
        # （load_profile_from_db 返回键：allergen_codes/dietary_restrictions/
        #  special_population/equipment；难度上限单独读 user_skill_profile）
        db_profile: dict = {}
        difficulty_cap: int | None = None
        if user_id:
            db_profile = load_profile_from_db(session, user_id)
            difficulty_cap = _load_difficulty_cap(session, user_id)
        profile = SafetyProfile(
            user_allergen_codes=[str(c) for c in (db_profile.get("allergen_codes") or [])],
            dietary_restrictions=[str(c) for c in (db_profile.get("dietary_restrictions") or [])],
            special_population=[str(c) for c in (db_profile.get("special_population") or [])],
            difficulty_cap=difficulty_cap,
            equipment=[str(e) for e in (db_profile.get("equipment") or [])],
        )

        # 候选 → 布尔硬过滤（🔴 零输入必过，逐维计数供前端展示）
        exclude_ids = _normalize_exclude_ids(payload.exclude_ids or [])
        candidates = _load_candidates(session, exclude_ids)
        filtered, counts = hard_filter(session, candidates, profile)
        body["filtered_by"] = counts

        # 排序 + 稳定随机扰动，取 ≤6 条组装结果（字段对齐 RecommendResultItem）
        picked = _pick_top_candidates(filtered, exclude_ids)
        results: list[dict] = []
        for idx, cand in enumerate(picked):
            allergens = sorted(
                set(list(cand.get("allergen_codes") or []) + list(cand.get("ingredient_allergen_codes") or []))
            )
            results.append(
                {
                    "recipe_id": int(cand["recipe_id"]),
                    "title": str(cand.get("title") or ""),
                    "match_level": "can_cook_now",
                    "covered_ingredients": [],
                    "missing_ingredients": [],
                    "time_minutes": int(cand["time_minutes"]) if cand.get("time_minutes") else None,
                    "difficulty": difficulty_label(cand.get("difficulty")),
                    "calories_kcal": cand.get("calories_kcal"),
                    "allergens": allergens,
                    "required_equipment": list(cand.get("equipment") or []),
                    "rank_score": round(1.0 - idx * 0.01, 4),
                    "rank_reasons": _build_rank_reasons(cand),
                    "source": str(cand.get("source_label") or "") or None,
                    "cover_image_url": cand.get("cover_image_url"),
                }
            )
        body["results"] = results
    except Exception as exc:  # noqa: BLE001 —— 降级约定：HTTP 恒 200 + 空结果
        logger.warning("day menu recommend failed: %s", exc)
        body["results"] = []
        body["filtered_by"] = body.get("filtered_by") or {}
    if not body["results"]:
        body["notice"] = _EMPTY_NOTICE
    return JSONResponse(
        content=json.loads(json.dumps(body, ensure_ascii=False, default=str)),
        headers={"X-Request-Id": rid},
    )
