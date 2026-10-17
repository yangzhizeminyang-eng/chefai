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
      ≤2 −0.1，夹 [0.1, 3.0]）；
    POST /v1/innovation/jobs：提交异步生成任务（202 立即返回 job_id，M-01：
      LLM 上游慢时同步长请求连接挂死，改「提交 + 轮询」链路）；
    GET  /v1/innovation/jobs/{job_id}：轮询异步任务状态（succeeded 取 recipe /
      failed 取 error / blocked 取 issues；未知/他人 job 统一 404）。

    🔴 阶段一设计取舍（异步 job store）：单进程内存字典 + 锁——演示环境单进程
    部署，进程重启后 job 丢失（客户端轮询 404 按失败重试即可恢复）；阶段二多
    副本部署再迁 DB 表 + 状态机（改进方案 M-01「job 表 + 状态机」），端点契约
    与跨用户隔离口径不变。同步 /generate 保留向后兼容，既有 7 端点零改动。

🔴 红线：
    - 所有响应含 is_ai_innovated=true 与 disclaimer 字段（AI 创新强制标识）；
    - switch.innovation=false → 全部 9 端点 503 {code: INNOVATION_MAINTENANCE}
      维护态（入口隐藏由前端处理，服务端统一拒绝）；
    - 搭配结论必须查表（子图实现），LLM 无权决定搭配。
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ability.embedding import upsert_embedding
from app.api.v1.deps import (
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    api_error,
    get_current_user,
    resolve_request_id,
)
from app.core.db import SessionLocal, get_db
from app.core.logging import get_logger
from app.graph.subgraphs.innovation import run_innovation_generate, run_innovation_precheck
from app.models import (
    FlavorPairingRule,
    InnovationJob,
    InnovationRecipe,
    RemoteConfig,
    User,
)
from app.schemas.innovation import (
    DISCLAIMER_TEXT,
    InnovationFeedbackRequest,
    InnovationFeedbackResponse,
    InnovationGenerateRequest,
    InnovationGenerateResponse,
    InnovationIssue,
    InnovationJobCreatedResponse,
    InnovationJobStatusResponse,
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
        LLM 表达调用带 25s 硬超时（LLM_HARD_TIMEOUT_SECONDS，P1 DEF-01：前端
        本接口专用 60s 超时，后端必须在其内返回）；LLM 超时/异常/量化违例时降级
        为「规则模板表达」（沿用配比模板量化用量 + 技法白名单 + 搭配依据拼装，
        量化校验代码强制，输出 100% 量化），响应结构完整不变；生成来源以
        basis.generated_by 标注：LLM 成功 = "llm"、降级 = "template"。

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


# ---------------------------------------------------------------------------
# 8)/9) 异步生成任务（M-01：LLM 上游慢（60s~2min）时同步长请求连接挂死，
#       改「提交即返回 job_id + 轮询终态」链路；同步 /generate 保留向后兼容）
# ---------------------------------------------------------------------------
# 异步 job 状态机（status 取值）：pending（已受理未执行）→ running（worker 执行中）
# → 终态三选一：succeeded（产出 recipe）/ failed（error 文案）/ blocked（风控拦截 issues）。
# 终态即冻结（不可逆），轮询方以终态为准收尾。

# 阶段一内存 job store：dict + 锁（🔴 读写一律持 _JOBS_LOCK，worker 与路由分属不同
# 线程）。job 记录结构：{job_id, user_db_id, status, recipe, issues, error,
# request_id, created_at, finished_at}。设计取舍：演示环境单进程部署；为满足进程
# 重启后的状态可恢复性，job 状态变更同步写穿 innovation_job 表（_persist_job_record，
# 失败仅告警不阻断链路），启动时遗留 pending/running 行统一置 failed
# （recover_stale_innovation_jobs），轮询方经 DB fallback 拿到明确终态而非 404。
_INNOVATION_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()

# 已完成 job 断线续查保留窗口（秒）：终态写入 finished_at，超窗 job 在新建时顺手清理
# （防 store 无界增长；10 分钟足够前端断线重连后补查一次结果）。
_JOB_RETENTION_SECONDS = 600

# 异步 job 执行线程池：LLM 25s 硬超时 + template 降级已在 job 内兜底（单任务最长
# 数十秒），max_workers=4 满足演示环境并发；线程名前缀便于日志定位。
_INNOVATION_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="innov-job")

# job 执行失败兜底文案（failed 终态面向用户话术，不透出内部异常细节）
_JOB_FAILED_MESSAGE = "AI 创新生成失败，请稍后重试"

# 服务重启恢复时写入 failed 终态的文案（面向轮询方，指引重新提交）
_JOB_RECOVER_MESSAGE = "服务已重启，任务被中断，请重新提交"


def _persist_job_record(record: dict) -> None:
    """把内存 job 记录写穿到 innovation_job 表（函数，独立短会话）。

    说明：
        在提交（pending）/转 running/终态变更三个时机同步调用，保证进程
        重启后 DB 中留有任务状态的最新快照；使用独立 SessionLocal 短会话
        （调用方持 _JOBS_LOCK，不与请求会话/worker 会话共享）；任何写穿
        失败仅记 WARNING——落库是尽力而为的增强，绝不阻断 job 主链路。

    参数：
        record：内存 job 记录 dict（结构见 _INNOVATION_JOBS 注释）。

    返回值：
        None。

    异常：
        不抛出（数据库异常捕获告警后返回）。
    """
    try:
        with SessionLocal() as session:
            row = session.query(InnovationJob).filter(
                InnovationJob.job_id == str(record.get("job_id"))
            ).one_or_none()
            finished_ts = record.get("finished_at")
            values = {
                "user_id": int(record.get("user_db_id") or 0),
                "status": str(record.get("status") or "pending"),
                "request_id": record.get("request_id"),
                "recipe": record.get("recipe"),
                "issues": list(record.get("issues") or []) or None,
                "error": record.get("error"),
                "finished_at": (
                    datetime.fromtimestamp(float(finished_ts), tz=datetime.UTC)
                    if finished_ts is not None else None
                ),
            }
            if row is None:
                session.add(InnovationJob(job_id=str(record.get("job_id")), **values))
            else:
                for key, val in values.items():
                    setattr(row, key, val)
            session.commit()
    except Exception as exc:  # noqa: BLE001 —— 写穿失败不阻断 job 主链路
        logger.warning("innovation job persist failed (job_id=%s): %s", record.get("job_id"), exc)


def recover_stale_innovation_jobs() -> int:
    """应用启动时恢复遗留的创新异步任务（函数）。

    说明：
        把 innovation_job 表中遗留的 pending/running 行统一置为 failed
        （error=_JOB_RECOVER_MESSAGE，finished_at=now）——进程重启后这些
        任务的 worker 线程已不存在，永不自行到终态；置为明确终态后轮询方
        经 get_innovation_job 的 DB fallback 可拿到失败文案。终态行不动
        （终态即冻结）。在 FastAPI startup 钩子调用（main.py on_startup）。

    返回值：
        int：被恢复（置 failed）的行数。

    异常：
        不抛出（数据库异常告警后返回 0——恢复失败不阻断应用启动）。
    """
    try:
        with SessionLocal() as session:
            stale_rows = session.query(InnovationJob).filter(
                InnovationJob.status.in_(("pending", "running"))
            ).all()
            for row in stale_rows:
                row.status = "failed"
                row.error = _JOB_RECOVER_MESSAGE
                row.finished_at = func.now()
            session.commit()
            if stale_rows:
                logger.warning(
                    "recovered %s stale innovation jobs (pending/running -> failed)",
                    len(stale_rows),
                )
            return len(stale_rows)
    except Exception as exc:  # noqa: BLE001 —— 恢复失败不阻断启动
        logger.warning("recover stale innovation jobs failed: %s", exc)
        return 0


def _cleanup_finished_jobs_locked(now_ts: float) -> None:
    """清理超过保留窗口的已完成 job（函数，调用方必须已持有 _JOBS_LOCK）。

    说明：
        仅回收 finished_at 非空且超 _JOB_RETENTION_SECONDS 的终态 job；
        pending/running 未到终态永不回收（避免轮询方拿到「凭空消失」的任务）。

    参数：
        now_ts：当前时间戳（time.time()，秒）。

    返回值：
        None。

    异常：
        无（纯内存遍历）。
    """
    deadline = now_ts - _JOB_RETENTION_SECONDS
    stale_ids = [
        job_id
        for job_id, record in _INNOVATION_JOBS.items()
        if record.get("finished_at") is not None and float(record["finished_at"]) < deadline
    ]
    for job_id in stale_ids:
        _INNOVATION_JOBS.pop(job_id, None)
    if stale_ids:
        logger.info("innovation jobs cleaned up: %s", stale_ids)


def _finish_job_locked(job_id: str, status: str, *, recipe: dict | None = None,
                       issues: list[dict] | None = None, error: str | None = None,
                       request_id: str | None = None) -> None:
    """把 job 写入终态（函数，调用方必须已持有 _JOBS_LOCK）。

    说明：
        终态写入即冻结（succeeded / failed / blocked 不可逆），同时记录
        finished_at（供断线续查窗口清理）与幂等键回显。

    参数：
        job_id：异步任务 ID。
        status：终态（succeeded / failed / blocked）。
        recipe：创新菜响应 dict（仅 succeeded 提供）。
        issues：拦截原因列表（blocked / failed 时可提供）。
        error：失败文案（仅 failed 提供）。
        request_id：幂等键回显（编排层可能重新生成，优先取其返回值）。

    返回值：
        None。

    异常：
        无（job 记录在提交时已建立，查无记录静默跳过——进程级 store 被外部清空
        的防御分支）。
    """
    record = _INNOVATION_JOBS.get(job_id)
    if record is None:
        return
    record["status"] = status
    record["recipe"] = recipe
    record["issues"] = list(issues or [])
    record["error"] = error
    record["request_id"] = request_id or record.get("request_id")
    record["finished_at"] = time.time()
    # 终态写穿（独立短会话，失败仅告警）：进程重启后轮询方经 DB fallback 拿终态
    _persist_job_record(record)


def _run_innovation_job(job_id: str, user_db_id: int, ingredients: list[str],
                        request_id: str, user_id_hash: str | None) -> None:
    """异步 job 执行体（线程池 worker 函数）。

    说明：
        执行 run_innovation_generate（🔴 自管 DB session，本函数不开新 session）：
        blocked=True → status=blocked 存 issues（拦截语义与同步接口一致）；
        有 result → succeeded 存 recipe（完整创新菜结构，is_ai_innovated 与
        disclaimer 恒带）；blocked=False 但无 result（子图兜底响应）→ failed 存
        error 文案。run_innovation_generate 理论上不抛异常（内部全捕获 + 25s
        LLM 硬超时 + template 降级兜底），此处再防御性兜底 failed，保证 job 必达
        终态（轮询方永不悬挂）。

    参数：
        job_id：异步任务 ID。
        user_db_id：用户数据库 ID（提交时在请求线程提取，避免 worker 访问已关闭
          请求会话的 ORM 实例）。
        ingredients：食材名列表。
        request_id：幂等键（透传编排层取证）。
        user_id_hash：用户标识哈希（sha256 前 12 位，trace 落库脱敏）。

    返回值：
        None。

    异常：
        不向外抛出（全捕获兜底为 failed 终态）。
    """
    with _JOBS_LOCK:
        record = _INNOVATION_JOBS.get(job_id)
        if record is not None:
            record["status"] = "running"
            # 转 running 写穿（同上，尽力而为）
            _persist_job_record(record)
    try:
        outcome = run_innovation_generate(
            user_db_id=int(user_db_id),
            ingredients=[str(i) for i in ingredients],
            request_id=request_id,
            user_id_hash=user_id_hash,
        )
    except Exception as exc:  # noqa: BLE001 —— 防御性兜底（编排层理论上不抛）
        logger.error("innovation job crashed (job_id=%s, request_id=%s): %s", job_id, request_id, exc)
        with _JOBS_LOCK:
            _finish_job_locked(job_id, "failed", error=_JOB_FAILED_MESSAGE)
        return

    with _JOBS_LOCK:
        if outcome.get("blocked"):
            # 风控拦截：终态 blocked + 拦截原因（前端展示拦截卡）
            _finish_job_locked(
                job_id,
                "blocked",
                issues=_issues_body(outcome.get("issues")),
                request_id=outcome.get("request_id"),
            )
        elif outcome.get("result"):
            # 生成成功：完整创新菜结构（与同步 /generate 的 recipe 同构）
            _finish_job_locked(
                job_id,
                "succeeded",
                recipe=outcome["result"],
                request_id=outcome.get("request_id"),
            )
        else:
            # 非 blocked 但无产出（子图异常兜底响应）：按失败语义
            logger.warning(
                "innovation job produced no result (job_id=%s, request_id=%s)", job_id, request_id
            )
            _finish_job_locked(
                job_id,
                "failed",
                issues=_issues_body(outcome.get("issues")),
                error=_JOB_FAILED_MESSAGE,
                request_id=outcome.get("request_id"),
            )


@router.post("/jobs", response_model=InnovationJobCreatedResponse, summary="提交 AI 创新异步生成任务（202 立即受理）")
def post_innovation_job(
    payload: InnovationGenerateRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """提交创新异步生成任务端点（函数）。

    说明：
        M-01 异步化：同步 /generate 在 LLM 上游慢（60s~2min）时长时间占用连接；
        本端点维护态校验通过后立即返回 202 {job_id, status:"pending", request_id}，
        生成在模块级线程池执行（run_innovation_generate 的 25s LLM 硬超时 +
        template 降级在 job 内兜底不变），前端持 job_id 轮询
        GET /v1/innovation/jobs/{job_id} 取终态。同步 /generate 保留向后兼容，
        请求体与其同构（ingredients ≥1）。

        🔴 阶段一设计取舍：单进程内存 job store（dict + 锁），演示环境单进程部署；
        进程重启后 job 丢失（客户端轮询 404 按失败重试即可恢复）；阶段二多副本
        部署再迁 DB 表 + 状态机（改进方案 M-01「job 表 + 状态机」），端点契约与
        跨用户隔离口径不变。新建 job 时顺手清理 finished_at 超过 10 分钟的已完成
        job（断线续查窗口）。

    参数：
        payload：生成请求体（ingredients ≥1，与同步 /generate 同构）。
        request：FastAPI 请求对象（读身份头/幂等键）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：202 {job_id, status:"pending", request_id} / 503 维护态。

    异常：
        不向外抛业务异常（身份解析/数据库异常由全局异常处理器兜底）。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    rid = resolve_request_id(payload.request_id, request)
    job_id = f"injob_{uuid.uuid4().hex[:12]}"
    now_ts = time.time()
    with _JOBS_LOCK:
        # 顺手清理断线续查窗口之外的已完成 job（持锁内回收，防 store 无界增长）
        _cleanup_finished_jobs_locked(now_ts)
        _INNOVATION_JOBS[job_id] = {
            "job_id": job_id,
            "user_db_id": int(user.id),
            "status": "pending",
            "recipe": None,
            "issues": [],
            "error": None,
            "request_id": rid,
            "created_at": now_ts,
            "finished_at": None,
        }
        # 提交即写穿 pending 快照（独立短会话，失败仅告警）：
        # 保证重启恢复扫描能看到本任务（终态前任何时刻重启都可恢复）
        _persist_job_record(_INNOVATION_JOBS[job_id])
    # 提交线程池（fire-and-forget）：worker 全捕获必达终态，future 无需消费；
    # 用户标识在请求线程提取（worker 不触碰已关闭请求会话的 ORM 实例）
    _INNOVATION_JOB_EXECUTOR.submit(
        _run_innovation_job,
        job_id,
        int(user.id),
        [str(i) for i in payload.ingredients],
        rid,
        _user_hash(user),
    )
    logger.info("innovation job submitted (job_id=%s, request_id=%s)", job_id, rid)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "pending", "request_id": rid},
        headers={"X-Request-Id": rid},
    )


@router.get("/jobs/{job_id}", response_model=InnovationJobStatusResponse, summary="查询 AI 创新异步生成任务状态（轮询）")
def get_innovation_job(
    job_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> InnovationJobStatusResponse | JSONResponse:
    """查询创新异步任务状态端点（函数）。

    说明：
        轮询返回任务状态：pending（已受理未执行）/ running（执行中）/ succeeded
        （recipe 为完整创新菜结构，🔴 is_ai_innovated=true 与 disclaimer 恒带）/
        failed（error 为面向用户文案）/ blocked（issues 为拦截原因）。终态即冻结，
        轮询方可安全停止。🔴 跨用户隔离：不存在与他人的 job 统一 404（不泄露
        存在性）；阶段一内存 store 进程重启后 job 丢失 → 404（客户端按失败重试），
        阶段二迁 DB 表后语义不变（改进方案 M-01「job 表 + 状态机」）。

    参数：
        job_id：异步任务 ID（POST /v1/innovation/jobs 返回）。
        request：FastAPI 请求对象（读身份头）。
        session：请求级数据库会话。

    返回值：
        InnovationJobStatusResponse | JSONResponse：200 任务状态 / 404（未知或他人
        job）/ 503 维护态。

    异常：
        HTTPException 404（统一错误 JSON）；身份解析/数据库异常由全局处理器兜底。
    """
    if not _innovation_switch_on(session):
        return _maintenance_response()
    user = get_current_user(request, session)
    with _JOBS_LOCK:
        # 持锁内浅拷贝快照（worker 终态为整块引用替换，快照无写撕裂）
        record = _INNOVATION_JOBS.get(job_id)
        snapshot = dict(record) if record is not None else None
    if snapshot is None:
        # 内存 miss → DB fallback（进程重启后内存 store 清空，持久化行兜底）：
        # 同用户的任务返回 DB 快照（重启遗留任务已被启动恢复置 failed 终态），
        # 未知/他人 job 仍统一 404（跨用户隔离口径不变）
        row = session.query(InnovationJob).filter(
            InnovationJob.job_id == job_id
        ).one_or_none()
        if row is not None and int(row.user_id) == int(user.id):
            snapshot = {
                "job_id": row.job_id,
                "user_db_id": int(row.user_id),
                "status": str(row.status),
                "recipe": row.recipe,
                "issues": list(row.issues or []),
                "error": row.error,
                "request_id": row.request_id,
                "created_at": None,
                "finished_at": None,
            }
    if snapshot is None or int(snapshot.get("user_db_id") or 0) != int(user.id):
        # 🔴 不存在与他人的 job 统一 404（跨用户隔离，不泄露存在性）
        raise api_error(404, ERR_NOT_FOUND, "任务不存在", f"job_id={job_id}")
    recipe = snapshot.get("recipe")
    return InnovationJobStatusResponse(
        job_id=job_id,
        status=str(snapshot.get("status") or "pending"),
        recipe=InnovationRecipeOut(**recipe) if isinstance(recipe, dict) else None,
        issues=list(snapshot.get("issues") or []),
        error=snapshot.get("error"),
        request_id=snapshot.get("request_id"),
    )
