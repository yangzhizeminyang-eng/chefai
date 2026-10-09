"""后台日志查询路由模块（模块 K）。

职责：
    - GET /admin/v1/trace-logs：agent_trace 四维过滤（start/end 时间、node_name、
      status、rule_hit）分页查询；user 维度仅回 user_id_hash（NFR-7.4 脱敏）；
    - GET /admin/v1/operation-logs：后台操作审计分页（module 过滤）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import page_args
from app.core.db import get_db
from app.models import AgentTrace, OperationLog

router = APIRouter(tags=["后台-日志查询"])

# 默认时间窗（天）：start 未传时向前追溯范围
_DEFAULT_RANGE_DAYS = 7


@router.get("/trace-logs", summary="Agent 调用日志四维过滤查询")
def list_trace_logs(
    start: datetime | None = None,
    end: datetime | None = None,
    node_name: str | None = None,
    status: str | None = None,
    rule_hit: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """trace 日志查询端点（函数）。

    说明：
        时间窗口闭区间 [start, end]（缺省 start=now-7d）；user 脱敏：模型仅存
        user_id_hash，直接透出该字段（无裸 user_id 可泄露）。

    参数：
        start：起始时间（ISO 8601，可 None）。
        end：结束时间（可 None=now）。
        node_name：节点名过滤（可 None）。
        status：七态状态过滤（可 None）。
        rule_hit：命中规则过滤（可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}；item 含 request_id/user_id_hash/node_name/status/
        duration_ms/prompt_tokens/completion_tokens/cost_cents/rule_hit/created_at。

    异常：
        422：时间格式非法（FastAPI 自动校验）。
    """
    offset, limit = offset_limit
    end_bound = end or datetime.now(UTC) + timedelta(minutes=1)
    start_bound = start or (end_bound - timedelta(days=_DEFAULT_RANGE_DAYS))
    conds = [AgentTrace.created_at >= start_bound, AgentTrace.created_at <= end_bound]
    if node_name:
        conds.append(AgentTrace.node_name == node_name)
    if status:
        conds.append(AgentTrace.status == status)
    if rule_hit:
        conds.append(AgentTrace.rule_hit == rule_hit)
    base = select(AgentTrace).where(*conds)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(
        base.order_by(AgentTrace.created_at.desc(), AgentTrace.id.desc())
        .offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": int(t.id),
                "request_id": t.request_id,
                "user_id_hash": t.user_id_hash,  # 脱敏口径：仅回哈希字段
                "node_name": t.node_name,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "prompt_tokens": t.prompt_tokens,
                "completion_tokens": t.completion_tokens,
                "cost_cents": float(t.cost_cents) if t.cost_cents is not None else 0.0,
                "rule_hit": t.rule_hit,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
        "total": int(total),
    }


@router.get("/operation-logs", summary="后台操作审计分页")
def list_operation_logs(
    module: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """操作日志查询端点（函数）。

    参数：
        module：业务模块过滤（可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}；item 含 id/admin_user_id/module/action/target_type/
        target_id/before_snapshot/after_snapshot/ip/created_at。

    异常：
        无。
    """
    offset, limit = offset_limit
    base = select(OperationLog)
    if module:
        base = base.where(OperationLog.module == module)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(
        base.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        .offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": int(log.id),
                "admin_user_id": int(log.admin_user_id) if log.admin_user_id else None,
                "module": log.module,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": int(log.target_id) if log.target_id is not None else None,
                "before_snapshot": log.before_snapshot,
                "after_snapshot": log.after_snapshot,
                "ip": str(log.ip) if log.ip else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in rows
        ],
        "total": int(total),
    }
