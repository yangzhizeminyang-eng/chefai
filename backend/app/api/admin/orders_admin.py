"""后台订单管理路由模块（模块 K，super_admin 专属）。

职责：
    - GET /admin/v1/orders?status=&page=：订单分页列表；
    - POST /admin/v1/orders/{order_no}/compensate {reason, target_status?}：
      人工补发——仅 failed/closed 可补发（target_status 缺省 paid，可选
      refunded），reason 必填落审计日志（module='order'）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import ERR_NOT_FOUND, ERR_VALIDATION, api_error, page_args
from app.core.db import get_db
from app.core.security import require_super, write_operation_log
from app.models import Order
from app.schemas.admin import OrderCompensateRequest

router = APIRouter(prefix="/orders", tags=["后台-订单管理"])

_MODULE = "order"

# 允许发起补发的订单状态
_COMPENSATABLE = ("failed", "closed")

# 订单审计快照字段
_ORDER_FIELDS = (
    "order_no", "user_id", "product_type", "amount_cents",
    "currency", "status", "wx_transaction_id",
)


def _order_snapshot(order: Order) -> dict:
    """订单审计快照（函数）。

    参数：
        order：订单 ORM 实例。

    返回值：
        dict：关键字段字典（金额以分保留）。

    异常：
        无。
    """
    return {
        field: getattr(order, field) for field in _ORDER_FIELDS
    } | {
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


@router.get("", summary="订单分页列表")
def list_orders(
    status: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """订单列表端点（函数）。

    参数：
        status：状态过滤（pending/paid/failed/refunded/closed，可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}。

    异常：
        无。
    """
    offset, limit = offset_limit
    base = select(Order)
    if status:
        base = base.where(Order.status == status)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(
        base.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [_order_snapshot(o) | {"id": int(o.id)} for o in rows],
        "total": int(total),
    }


@router.post("/{order_no}/compensate", summary="订单人工补发（failed/closed → paid/refunded）")
def compensate_order(
    order_no: str,
    payload: OrderCompensateRequest,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """订单补发端点（函数）。

    说明：
        仅 failed/closed 可补发；target_status 缺省 paid（置 paid_at=now），
        可选 refunded；reason 必填（审计追责）。before/after 快照写日志。

    参数：
        order_no：商户订单号（唯一）。
        payload：{reason, target_status?}。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{order_no, from_status, status}。

    异常：
        HTTPException 404：订单不存在；422：状态不允许补发；403：非超管。
    """
    order = session.execute(
        select(Order).where(Order.order_no == order_no)
    ).scalar_one_or_none()
    if order is None:
        raise api_error(404, ERR_NOT_FOUND, "订单不存在", f"order_no={order_no}")
    if order.status not in _COMPENSATABLE:
        raise api_error(
            422, ERR_VALIDATION,
            f"订单状态 {order.status} 不允许补发（仅 failed/closed）",
            f"order_no={order_no}",
        )
    before = _order_snapshot(order)
    from_status = order.status
    order.status = payload.target_status
    if payload.target_status == "paid":
        # 用 Python 时间而非 func.now()：快照序列化需要具体 datetime 值
        order.paid_at = datetime.now(UTC)
    write_operation_log(
        session, admin, _MODULE, "compensate",
        target_type="order", target_id=int(order.id),
        before=before,
        after=_order_snapshot(order) | {"reason": payload.reason},
        request=request,
    )
    session.commit()
    return {"order_no": order_no, "from_status": from_status, "status": order.status}
