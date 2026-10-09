"""AI 菜品创新路由模块（模块 O，7 接口）。

职责：
    POST /v1/innovation/precheck：预检（高危/过敏原/特殊人群/taboo 四类拦截语义）；
    POST /v1/innovation/generate：生成（前置自动复用 precheck 同一核心函数，成功 201）；
    GET  /v1/innovation/recipes/{id}：本人私有详情（他人 404，disclaimer 恒带）；
    POST /v1/innovation/recipes/{id}/adopt：采纳（状态机 generated→adopted，非法 422）；
    POST /v1/innovation/recipes/{id}/index：入向量索引（adopted→indexed，写
      source='ai_private' 私有向量分区）；
    POST /v1/innovation/recipes/{id}/reuse：复用（本人 indexed/adopted，跨用户隔离）；
    POST /v1/innovation/recipes/{id}/feedback：评分回流（rating≥4 规则权重 +0.1、
      ≤2 −0.1，夹 [0.1, 3.0]）。

🔴 红线：
    - 所有响应含 is_ai_innovated=true 与 disclaimer 字段（AI 创新强制标识）；
    - switch.innovation=false → 全部 7 端点 503 {code: INNOVATION_MAINTENANCE}
      维护态（入口隐藏由前端处理，服务端统一拒绝）；
    - 搭配结论必须查表（子图实现），LLM 无权决定搭配。
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ability.embedding import upsert_embedding
from app.api.v1.deps import (
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    api_error,
    get_current_user,
    resolve_request_id,
)
from app.core.db import get_db
from app.core.logging import get_logger
from app.graph.subgraphs.innovation import run_innovation_generate, run_innovation_precheck
from app.models import FlavorPairingRule, InnovationRecipe, RemoteConfig, User
from app.schemas.innovation import (
    DISCLAIMER_TEXT,
    InnovationFeedbackRequest,
    InnovationFeedbackResponse,
    InnovationGenerateRequest,
    InnovationGenerateResponse,
    InnovationIssue,
    InnovationPrecheckRequest,
    InnovationPrecheckResponse,
    InnovationRecipeOut,
    InnovationReuseResponse,
    InnovationStateActionResponse,
)

router = APIRouter(prefix="/innovation", tags=["AI 菜品创新"])

logger = get_logger(__name__)

# switch.innovation 维护态错误码与文案（全部 7 端点统一 503）
_ERR_MAINTENANCE = "INNOVATION_MAINTENANCE"
_MSG_MAINTENANCE = "AI 创新功能维护中"

# 状态机合法流转表（🔴 单向：generated → adopted → indexed；removed 为终态删除标记）
_VALID_TRANSITIONS: dict[str, str] = {"generated": "adopted", "adopted": "indexed"}


def _innovation_switch_on(session: Session) -> bool:
    """读 switch.innovation 开关（函数）。

    说明：
        每请求直查 remote_config（与 config.get_switches / member 同语义：行缺省/
        值非法/查询异常均回退 True），60s 内生效且不引入缓存。

    参数：
        session：请求级数据库会话。

    返回值：
        bool：开关状态（缺省 True）。

    异常：
        不抛出（异常回退 True）。
    """
    try:
        value = session.execute(
            select(RemoteConfig.value).where(RemoteConfig.config_key == "switch.innovation")
        ).scalar_one_or_none()
        return bool(value) if isinstance(value, bool) else True
    except Exception as exc:  # noqa: BLE001 —— 开关读取失败回退开启
        logger.warning("innovation switch read failed: %s", exc)
        return True


def _maintenance_response() -> JSONResponse:
    """构造维护态 503 响应（函数）。

    返回值：
        JSONResponse：503 {code: INNOVATION_MAINTENANCE, message: AI 创新功能维护中}。

    异常：
        无。
    """
    return JSONResponse(
        status_code=503,
        content={"code": _ERR_MAINTENANCE, "message": _MSG_MAINTENANCE, "detail": None},
    )


def _issues_body(issues: list[dict] | None) -> list[dict]:
    """把编排层 issues 归一为响应结构（函数）。

    参数：
        issues：编排层拦截原因列表（[{type, message}]，可 None）。

    返回值：
        list[dict]：InnovationIssue 兼容结构列表。

    异常：
        无。
    """
    return [InnovationIssue(**item).model_dump() for item in (issues or [])]


def _user_hash(user: User) -> str:
    """计算用户标识哈希（函数）。

    说明：
        与 runner 同口径：sha256(anonymous_id).hexdigest()[:12]（脱敏，不入原文）；
        匿名 ID 缺失时以用户主键兜底。

    参数：
        user：当前用户 ORM 实例。

    返回值：
        str：12 位哈希。

    异常：
        无。
    """
    key = str(user.anonymous_id or user.id)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _recipe_out(row: InnovationRecipe) -> dict:
    """InnovationRecipe ORM → 响应字典（函数）。

    说明：
        🔴 恒带 is_ai_innovated=true 与 disclaimer（强制标识红线）；时间字段 ISO 化。

    参数：
        row：创新菜 ORM 实例。

    返回值：
        dict：InnovationRecipeOut 兼容结构。

    异常：
        无。
    """
    return {
        "id": int(row.id),
        "name": str(row.name),
        "ingredients": list(row.ingredients or []),
        "steps": list(row.steps or []),
        "basis": dict(row.basis or {}),
        "nutrition": dict(row.nutrition or {}),
        "status": str(row.status),
        "is_ai_innovated": bool(row.is_ai_innovated),
        "visibility": str(row.visibility),
        "disclaimer": DISCLAIMER_TEXT,
        "rating": int(row.rating) if row.rating is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _get_owned_recipe(session: Session, user_id: int, recipe_id: int) -> InnovationRecipe | None:
    """查询本人创新菜（函数，跨用户隔离口径）。

    说明：
        🔴 跨用户隔离：仅按 (id, user_id) 命中，他人资源与不存在资源统一返回
        None（对外均表现为 404，不泄露存在性）。

    参数：
        session：请求级数据库会话。
        user_id：当前用户数据库 ID。
        recipe_id：创新菜 ID。

    返回值：
        InnovationRecipe | None：本人创新菜实例；他人/不存在返回 None。

    异常：
        查询异常向上抛出（由全局异常处理器兜底）。
    """
    return session.execute(
        select(InnovationRecipe)
        .where(InnovationRecipe.id == int(recipe_id))
        .where(InnovationRecipe.user_id == int(user_id))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# 1) 预检
# ---------------------------------------------------------------------------
@router.post("/precheck", response_model=InnovationPrecheckResponse, summary="AI 创新预检（高危/过敏原/特殊人群/taboo）")
def post_innovation_precheck(
    payload: InnovationPrecheckRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationPrecheckResponse | JSONResponse:
    """创新预检端点（函数）。

    说明：
        复用 run_innovation_precheck 核心（与 generate 前置检查同一函数）；维护态
        503；身份走 X-Anonymous-Id 惯例（get_current_user 自动 upsert 匿名用户，
        供档案类拦截读取家庭过敏原/特殊人群并集）。

    参数：
        payload：预检请求体（ingredients ≥1）。
        request：FastAPI 请求对象（读身份头/幂等键）。
        session：请求级数据库会话。

    返回值：
        InnovationPrecheckResponse | JSONResponse：200 预检结果（含命中的推荐搭配
        依据 pairings）/ 503 维护态。

    异常：
        编排层全捕获（异常按拦截处理），本端点不向外抛业务异常。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    rid = resolve_request_id(payload.request_id, request)
    pre = run_innovation_precheck(int(user.id), list(payload.ingredients), rid)
    return InnovationPrecheckResponse(
        ok=bool(pre["ok"]),
        blocked=bool(pre["blocked"]),
        issues=_issues_body(pre["issues"]),
        risk_log_written=bool(pre["risk_log_written"]),
        pairings=list(pre.get("pairings") or []) or None,
    )


# ---------------------------------------------------------------------------
# 2) 生成
# ---------------------------------------------------------------------------
@router.post("/generate", response_model=InnovationGenerateResponse, summary="AI 创新生成（预检 + 受约束生成 + 落库）")
def post_innovation_generate(
    payload: InnovationGenerateRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """创新生成端点（函数）。

    说明：
        生成前自动先跑 precheck 逻辑（run_innovation_generate 内部复用同一核心
        函数）：拦截 → 200 {ok:false, blocked:true, issues, ...}；成功 → 201 创新菜
        完整结构（is_ai_innovated=true、disclaimer 恒带、basis 依据可追溯）。
        LLM 离线时子图自动降级本地模板（量化校验代码强制，输出 100% 量化）。

    参数：
        payload：生成请求体（ingredients ≥1）。
        request：FastAPI 请求对象（读身份头/幂等键）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：201 生成结果 / 200 拦截语义 / 503 维护态。

    异常：
        编排层全捕获兜底，本端点不向外抛业务异常。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    rid = resolve_request_id(payload.request_id, request)
    outcome = run_innovation_generate(
        user_db_id=int(user.id),
        ingredients=list(payload.ingredients),
        request_id=rid,
        user_id_hash=_user_hash(user),
    )
    if outcome.get("blocked") or not outcome.get("result"):
        body = {
            "ok": False,
            "blocked": bool(outcome.get("blocked")),
            "issues": _issues_body(outcome.get("issues")),
            "risk_log_written": bool(outcome.get("risk_log_written")),
            "request_id": outcome.get("request_id") or rid,
            "trace_id": outcome.get("trace_id"),
            "is_ai_innovated": True,
            "disclaimer": DISCLAIMER_TEXT,
        }
        return JSONResponse(content=body, headers={"X-Request-Id": rid})
    body = {
        "ok": True,
        "recipe": outcome["result"],
        "request_id": outcome.get("request_id") or rid,
        "trace_id": outcome.get("trace_id"),
    }
    return JSONResponse(status_code=201, content=body, headers={"X-Request-Id": rid})


# ---------------------------------------------------------------------------
# 3) 详情（本人私有）
# ---------------------------------------------------------------------------
@router.get("/recipes/{recipe_id}", response_model=InnovationRecipeOut, summary="AI 创新菜详情（本人私有）")
def get_innovation_recipe(
    recipe_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationRecipeOut | JSONResponse:
    """创新菜详情端点（函数）。

    说明：
        仅本人可见（他人/不存在统一 404）；removed 视为已删除（404）；
        disclaimer 恒带。

    参数：
        recipe_id：创新菜 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InnovationRecipeOut | JSONResponse：200 详情 / 404 / 503 维护态。

    异常：
        数据库异常向上抛出（全局处理器兜底）。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    row = _get_owned_recipe(session, int(user.id), recipe_id)
    if row is None or row.status == "removed":
        raise api_error(404, ERR_NOT_FOUND, "创新菜不存在", f"recipe_id={recipe_id}")
    return InnovationRecipeOut(**_recipe_out(row))


# ---------------------------------------------------------------------------
# 4) 采纳（generated → adopted）
# ---------------------------------------------------------------------------
@router.post("/recipes/{recipe_id}/adopt", response_model=InnovationStateActionResponse, summary="采纳创新菜（generated→adopted）")
def post_innovation_adopt(
    recipe_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationStateActionResponse | JSONResponse:
    """采纳端点（函数）。

    说明：
        状态机仅允许 generated→adopted（重复采纳/其他状态 422 非法流转）。

    参数：
        recipe_id：创新菜 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InnovationStateActionResponse | JSONResponse：200 {status: adopted} /
        404 / 422 / 503 维护态。

    异常：
        HTTPException 404/422（统一错误 JSON）。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    row = _get_owned_recipe(session, int(user.id), recipe_id)
    if row is None or row.status == "removed":
        raise api_error(404, ERR_NOT_FOUND, "创新菜不存在", f"recipe_id={recipe_id}")
    if _VALID_TRANSITIONS.get(row.status) != "adopted":
        raise api_error(
            422, ERR_CONFLICT, "创新菜状态不允许采纳", f"recipe_id={recipe_id}, status={row.status}"
        )
    row.status = "adopted"
    session.commit()
    return InnovationStateActionResponse(status="adopted")


# ---------------------------------------------------------------------------
# 5) 入向量索引（adopted → indexed）
# ---------------------------------------------------------------------------
@router.post("/recipes/{recipe_id}/index", response_model=InnovationStateActionResponse, summary="创新菜入私有向量索引（adopted→indexed）")
def post_innovation_index(
    recipe_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationStateActionResponse | JSONResponse:
    """入向量索引端点（函数）。

    说明：
        仅 adopted→indexed；调 upsert_embedding(source='ai_private', owner_user_id,
        innovation_recipe_id, embed_text=菜名+食材拼接) 写私有向量分区（表 CHECK
        红线强制 owner+innovation 双字段）；embedding 写入即 commit（同会话内
        状态变更一并提交）；按 innovation_recipe_id 幂等。

    参数：
        recipe_id：创新菜 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InnovationStateActionResponse | JSONResponse：200 {status: indexed,
        embedding_id} / 404 / 422 / 503 维护态。

    异常：
        HTTPException 404/422；embedding 写入异常向上抛出（全局处理器兜底）。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    row = _get_owned_recipe(session, int(user.id), recipe_id)
    if row is None or row.status == "removed":
        raise api_error(404, ERR_NOT_FOUND, "创新菜不存在", f"recipe_id={recipe_id}")
    if _VALID_TRANSITIONS.get(row.status) != "indexed":
        raise api_error(
            422, ERR_CONFLICT, "创新菜状态不允许入索引", f"recipe_id={recipe_id}, status={row.status}"
        )
    row.status = "indexed"
    session.flush()
    ingredient_names = " ".join(
        str(item.get("name") or "").strip() for item in (row.ingredients or []) if isinstance(item, dict)
    ).strip()
    embed_text = f"{row.name} {ingredient_names}".strip()
    embedding_id = upsert_embedding(
        session,
        owner_user_id=int(user.id),
        source="ai_private",
        innovation_recipe_id=int(row.id),
        embed_text=embed_text,
    )
    return InnovationStateActionResponse(status="indexed", embedding_id=int(embedding_id))


# ---------------------------------------------------------------------------
# 6) 复用（跨用户隔离）
# ---------------------------------------------------------------------------
@router.post("/recipes/{recipe_id}/reuse", response_model=InnovationReuseResponse, summary="复用创新菜（本人 indexed/adopted）")
def post_innovation_reuse(
    recipe_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationReuseResponse | JSONResponse:
    """复用端点（函数）。

    说明：
        本人 indexed/adopted 可复用（供前端直接进入分步引导/再编辑）；
        generated 未采纳 → 422；他人/不存在/removed → 404（🔴 跨用户隔离，
        不泄露他人资源存在性）。

    参数：
        recipe_id：创新菜 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InnovationReuseResponse | JSONResponse：200 {recipe} / 404 / 422 /
        503 维护态。

    异常：
        HTTPException 404/422（统一错误 JSON）。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    row = _get_owned_recipe(session, int(user.id), recipe_id)
    if row is None or row.status == "removed":
        raise api_error(404, ERR_NOT_FOUND, "创新菜不存在", f"recipe_id={recipe_id}")
    if row.status not in ("adopted", "indexed"):
        raise api_error(
            422, ERR_CONFLICT, "创新菜尚未采纳，暂不可复用", f"recipe_id={recipe_id}, status={row.status}"
        )
    return InnovationReuseResponse(recipe=InnovationRecipeOut(**_recipe_out(row)))


# ---------------------------------------------------------------------------
# 7) 反馈回流（评分 → 搭配规则权重调整）
# ---------------------------------------------------------------------------
@router.post("/recipes/{recipe_id}/feedback", response_model=InnovationFeedbackResponse, summary="创新菜评分回流（调整搭配规则权重）")
def post_innovation_feedback(
    recipe_id: int,
    payload: InnovationFeedbackRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationFeedbackResponse | JSONResponse:
    """评分回流端点（函数）。

    说明：
        更新 innovation_recipe.rating 并回流调整搭配规则权重：解析该创新菜
        basis.pairings 引用的 rule_id，rating≥4 → weight+0.1，rating≤2 →
        weight−0.1（rating=3 不调整），夹在 [0.1, 3.0]；removed → 404。

    参数：
        recipe_id：创新菜 ID。
        payload：反馈请求体（rating 1~5，comment 可选）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InnovationFeedbackResponse | JSONResponse：200 {status: ok,
        adjusted_rules} / 404 / 503 维护态。

    异常：
        HTTPException 404；数据库异常向上抛出（全局处理器兜底）。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    row = _get_owned_recipe(session, int(user.id), recipe_id)
    if row is None or row.status == "removed":
        raise api_error(404, ERR_NOT_FOUND, "创新菜不存在", f"recipe_id={recipe_id}")
    if payload.comment:
        # 表无 comment 列（阶段二仅 rating 生效），文字反馈仅记录日志不落库
        logger.info("innovation feedback comment (recipe_id=%s): %s", recipe_id, payload.comment[:100])

    row.rating = int(payload.rating)
    delta = 0.1 if payload.rating >= 4 else (-0.1 if payload.rating <= 2 else 0.0)
    adjusted = 0
    if delta:
        basis = dict(row.basis or {})
        rule_ids = [
            int(p.get("rule_id"))
            for p in (basis.get("pairings") or [])
            if isinstance(p, dict) and p.get("rule_id") is not None
        ]
        if rule_ids:
            rules = session.execute(
                select(FlavorPairingRule).where(FlavorPairingRule.id.in_(rule_ids))
            ).scalars().all()
            for rule in rules:
                new_weight = min(3.0, max(0.1, float(rule.weight) + delta))
                if abs(new_weight - float(rule.weight)) >= 0.001:
                    rule.weight = round(new_weight, 2)
                    adjusted += 1
    session.commit()
    return InnovationFeedbackResponse(status="ok", adjusted_rules=adjusted)
