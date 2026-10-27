"""用户行为埋点路由模块。

职责：
    POST /v1/track/events：批量接收客户端埋点（web-mini track.ts 缓冲整批上报，
    请求体 {events: [{name, props?, ts, request_id}]}）——
      - 单批条数 > settings.TRACK_BATCH_MAX → 422 整批拒绝；
      - 事件名白名单（客户端 38 事件 + 运维事件 app_error，可经
        TRACK_EVENT_WHITELIST 覆盖）：白名单外单条丢弃并计入 discarded；
      - 单条 props 剥离敏感键值（password/token/cookie/authorization/api_key
        等，递归所有层级）后再存储；剥离后 JSON 字节数 > TRACK_ITEM_MAX_BYTES
        → 单条丢弃并计入 discarded；
      - X-Anonymous-Id 头透传落库（resolve_anonymous_id 同口径），无头允许
        （anonymous_id 存 NULL 记纯匿名）；
      - 响应 {accepted, discarded}（部分丢弃不 4xx，埋点永不阻断主流程）。
    GET /v1/track/events：管理员审计查询（get_current_admin 守卫，非管理员
    统一 401），返回 {total, items:[...]} 按 id 倒序。

保留策略（惰性清理）：
    写入时按小时间隔触发一次清理检查（进程级时间戳，不挂启动钩子）：
    距上次检查 ≥1h 则删除 created_at 早于 now - TRACK_RETENTION_DAYS 的行，
    清理失败仅告警回滚，绝不阻断埋点接收。
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import ERR_VALIDATION, api_error, resolve_anonymous_id
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.security import get_current_admin
from app.models import AdminUser, TrackEvent
from app.schemas.track import TrackBatchRequest

router = APIRouter(prefix="/track", tags=["埋点"])

logger = get_logger(__name__)

# 事件名白名单内置默认：客户端 38 事件（web-mini/src/utils/track.ts
# TrackEventName 逐字一致，禁止改名破坏口径）+ 运维事件 app_error
DEFAULT_EVENT_WHITELIST: frozenset[str] = frozenset(
    {
        "app_enter",
        "disclaimer_agree",
        "ingredient_manual_select",
        "ingredient_photo_upload",
        "ingredient_recognize_result",
        "ingredient_recognize_correct",
        "recommend_request",
        "recommend_impression",
        "recommend_click",
        "filtered_by_allergen",
        "recipe_detail_view",
        "cook_start",
        "cook_step_next",
        "cook_voice_command",
        "cook_help_request",
        "cook_complete",
        "cook_abandon",
        "cook_rating",
        "nutrition_view",
        "inventory_add",
        "inventory_expiring_click",
        "safety_block",
        "medical_refuse",
        "search_no_result",
        "subscribe_click",
        "purchase_success",
        "feedback_submit",
        "innovation_enter",
        "innovation_precheck",
        "innovation_blocked",
        "innovation_generate",
        "innovation_result",
        "innovation_reason_view",
        "innovation_adopt",
        "innovation_cook",
        "innovation_feedback",
        "innovation_index",
        "innovation_reuse",
        # 运维事件：前端全局错误上报（口径外新增由白名单配置承载）
        "app_error",
    }
)

# 敏感键集合（键名小写比较；strip_sensitive 对 dict 递归所有层级剥离）
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "cookie",
        "cookies",
        "set-cookie",
        "authorization",
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "credential",
        "credentials",
        "session_key",
    }
)

# 惰性清理触发间隔（秒）：写入时每小时最多做一次清理检查
_PURGE_INTERVAL_SECONDS = 3600.0

# 上次清理检查时刻（time.monotonic；进程级，模块加载置 0 保证首个写请求必检查）
_last_purge_at: float = 0.0


def _event_whitelist() -> frozenset[str]:
    """解析当前生效的事件名白名单（函数）。

    说明：
        settings.TRACK_EVENT_WHITELIST 非空时按逗号分隔覆盖内置默认
        （每次请求现读，无缓存，配置改动即时生效且不引入状态）。

    返回值：
        frozenset[str]：白名单事件名集合（覆盖值为空串时回退内置默认）。

    异常：
        无。
    """
    raw = settings.TRACK_EVENT_WHITELIST.strip()
    if raw:
        names = frozenset(item.strip() for item in raw.split(",") if item.strip())
        if names:
            return names
    return DEFAULT_EVENT_WHITELIST


def strip_sensitive(value: Any) -> Any:
    """递归剥离敏感键值（函数）。

    说明：
        dict 按键名（大小写不敏感，命中 SENSITIVE_KEYS）整键删除，其余类型
        原样返回；list 逐元素递归；标量透传。返回新结构（不修改入参）。

    参数：
        value：任意 JSON 兼容值（props 或其子结构）。

    返回值：
        Any：剥离敏感键后的净值（结构/类型与入参同构）。

    异常：
        无。
    """
    if isinstance(value, dict):
        return {
            key: strip_sensitive(child)
            for key, child in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [strip_sensitive(child) for child in value]
    return value


def _props_bytes(props: dict) -> int:
    """计算 props JSON 序列化字节数（函数）。

    参数：
        props：剥离敏感后的事件属性。

    返回值：
        int：UTF-8 编码字节数（与 TRACK_ITEM_MAX_BYTES 比较口径）。

    异常：
        无（props 为 Pydantic 校验后的 JSON 兼容 dict，序列化不失败）。
    """
    return len(json.dumps(props, ensure_ascii=False).encode("utf-8"))


def _client_ts(ts: int | None) -> datetime | None:
    """毫秒时间戳 → UTC datetime（函数）。

    参数：
        ts：客户端本地毫秒时间戳（可 None）。

    返回值：
        datetime | None：UTC 时间；None/非正数/溢出时返回 None。

    异常：
        无（溢出/非法值统一吞掉按缺失处理）。
    """
    if not ts or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def purge_expired_track_events(session: Session, retention_days: int | None = None) -> int:
    """删除超保留期的事件行（函数）。

    说明：
        cutoff = now(UTC) - 保留天数；删除 created_at < cutoff 的全部行。
        供惰性清理（每写入请求按小时触发）与管理端手动清理复用。

    参数：
        session：数据库会话（由调用方提交/回滚）。
        retention_days：保留天数（None 时取 settings.TRACK_RETENTION_DAYS）。

    返回值：
        int：本次删除的行数。

    异常：
        SQLAlchemyError：数据库异常向上抛出（调用方决定回滚策略）。
    """
    days = settings.TRACK_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = session.execute(delete(TrackEvent).where(TrackEvent.created_at < cutoff))
    return int(result.rowcount or 0)


def _maybe_purge(session: Session) -> None:
    """写入路径的惰性清理检查（函数）。

    说明：
        距上次检查 ≥ _PURGE_INTERVAL_SECONDS 才执行 purge_expired_track_events；
        有删除才提交；失败告警回滚——清理属旁路维护，绝不阻断埋点接收。
        时间戳先推进再执行：失败也不立即重试，避免失败风暴。

    参数：
        session：请求级数据库会话。

    返回值：
        None。

    异常：
        不抛出（内部消化，仅告警日志）。
    """
    global _last_purge_at
    now = time.monotonic()
    if now - _last_purge_at < _PURGE_INTERVAL_SECONDS:
        return
    _last_purge_at = now
    try:
        if purge_expired_track_events(session) > 0:
            session.commit()
    except Exception as exc:  # noqa: BLE001 —— 清理失败回滚，不阻断写入
        session.rollback()
        logger.warning("track purge failed: %s", exc)


@router.post("/events", summary="批量接收埋点事件")
def receive_events(
    payload: TrackBatchRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """批量接收埋点端点（函数）。

    说明：
        白名单外/超 4KB 的条目丢弃并计数（响应 {accepted, discarded}），
        合法条目剥离敏感键后落库；批量超 TRACK_BATCH_MAX → 422 整批拒绝。
        入口先做惰性保留期清理检查。

    参数：
        payload：批量请求体（events 数组，元素 {name, props?, ts, request_id}）。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        dict：{"accepted": 接收条数, "discarded": 丢弃条数}。

    异常：
        HTTPException 422：批量条数超上限（api_error/VALIDATION_ERROR）；
        数据库异常向上抛出（全局处理器兜底）。
    """
    if len(payload.events) > settings.TRACK_BATCH_MAX:
        raise api_error(
            422,
            ERR_VALIDATION,
            f"单批事件数超过上限 {settings.TRACK_BATCH_MAX}",
            None,
        )

    _maybe_purge(session)

    anonymous_id = resolve_anonymous_id(None, request)
    whitelist = _event_whitelist()
    accepted = 0
    discarded = 0
    for item in payload.events:
        if item.name not in whitelist:
            discarded += 1
            continue
        props = strip_sensitive(item.props) if item.props else None
        if props is not None and _props_bytes(props) > settings.TRACK_ITEM_MAX_BYTES:
            discarded += 1
            continue
        session.add(
            TrackEvent(
                anonymous_id=anonymous_id,
                event_name=item.name,
                properties=props,
                request_id=item.request_id or None,
                client_ts=_client_ts(item.ts),
            )
        )
        accepted += 1
    session.commit()
    return {"accepted": accepted, "discarded": discarded}


@router.get("/events", summary="管理员查询埋点事件")
def list_events(
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    """管理员审计查询埋点端点（函数）。

    说明：
        get_current_admin 守卫（无凭证/伪造 token/账号禁用统一 401）；
        返回全量计数与最近 limit 条（按 id 倒序），字段已剥离敏感值
        （写入时保证）。

    参数：
        limit：返回条数上限（1~200，默认 50）。
        session：请求级数据库会话。
        admin：当前管理员（守卫依赖，仅鉴权用途）。

    返回值：
        dict：{"total": 总条数, "items": [事件行字典]}。

    异常：
        HTTPException 401：管理员凭证缺失/非法（get_current_admin）；
        数据库异常向上抛出（全局处理器兜底）。
    """
    total = int(
        session.execute(select(func.count()).select_from(TrackEvent)).scalar_one()
    )
    rows = (
        session.execute(select(TrackEvent).order_by(TrackEvent.id.desc()).limit(limit))
        .scalars()
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": row.id,
                "anonymous_id": row.anonymous_id,
                "event_name": row.event_name,
                "properties": row.properties,
                "request_id": row.request_id,
                "client_ts": row.client_ts.isoformat() if row.client_ts else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }
