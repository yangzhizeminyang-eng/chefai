"""后台反馈工单管理路由模块（模块 K，content_ops+）。

职责：
    - GET /admin/v1/feedbacks?status=&page=：工单分页列表；
    - POST /admin/v1/feedbacks/{id}/transition {action:'start'|'resolve'}：
      状态机 pending → processing → resolved（非法流转 422），
      全部流转写 operation_log（module='feedback'）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import ERR_NOT_FOUND, ERR_VALIDATION, api_error, page_args
from app.core.db import get_db
from app.core.security import require_writer, write_operation_log
from app.models import Feedback
from app.schemas.admin import FeedbackTransitionRequest

router = APIRouter(prefix="/feedbacks", tags=["后台-反馈工单"])

_MODULE = "feedback"

# 合法流转表：{当前状态: {action: 目标状态}}
_TRANSITIONS: dict[str, dict[str, str]] = {
    "pending": {"start": "processing"},
    "processing": {"resolve": "resolved"},
}


@router.get("", summary="反馈工单分页列表")
def list_feedbacks(
    status: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """工单列表端点（函数）。

    参数：
        status：状态过滤（pending/processing/resolved/ignored，可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}；item 不含 user_id（后台不暴露匿名用户内部 ID，
        仅回 session_request_id 关联取证）。

    异常：
        无。
    """
    offset, limit = offset_limit
    base = select(Feedback)
    if status:
        base = base.where(Feedback.status == status)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(
        base.order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": int(f.id),
                "type": f.type,
                "content": f.content,
                "images": list(f.images or []),
                "session_request_id": f.session_request_id,
                "status": f.status,
                "reply": f.reply,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in rows
        ],
        "total": int(total),
    }


@router.post("/{feedback_id}/transition", summary="工单流转（start/resolve）")
def transition_feedback(
    feedback_id: int,
    payload: FeedbackTransitionRequest,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """工单流转端点（函数）。

    说明：
        状态机：pending --start--> processing --resolve--> resolved；
        非法当前状态或非法动作组合 → 422 STATE_INVALID；流转写审计日志。

    参数：
        feedback_id：工单 ID。
        payload：{action: start|resolve}。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, from_status, status}。

    异常：
        HTTPException 404：工单不存在；422：非法流转；403：readonly。
    """
    fb = session.get(Feedback, feedback_id)
    if fb is None:
        raise api_error(404, ERR_NOT_FOUND, "工单不存在", f"feedback_id={feedback_id}")
    next_status = _TRANSITIONS.get(fb.status, {}).get(payload.action)
    if next_status is None:
        raise api_error(
            422, ERR_VALIDATION,
            f"当前状态 {fb.status} 不允许执行 {payload.action}",
            f"feedback_id={feedback_id}",
        )
    before = {"status": fb.status}
    fb.status = next_status
    write_operation_log(
        session, admin, _MODULE, payload.action,
        target_type="feedback", target_id=feedback_id,
        before=before, after={"status": next_status}, request=request,
    )
    session.commit()
    return {"id": feedback_id, "from_status": before["status"], "status": next_status}
