"""会员与支付路由模块（模块 J，模拟支付）。

职责：
    GET  /v1/member/plan：价目表预览（payment 开关关闭仍可访问）；
    GET  /v1/member/me：会员状态与当日识别额度（已购权益可查，不受开关影响）；
    POST /v1/member/orders：创建待支付订单（开关关闭 403）；
    POST /v1/member/orders/{order_no}/mock-pay：模拟支付回调（开关关闭 403）；
    GET  /v1/member/orders：本人订单列表（created_at 倒序）。

🔴 合规约束（J.4 / J.5）：
    - 支付渠道固定 pay_channel='miniprogram_virtual'（小程序虚拟支付）；
      政策提示 policy_note 明确「请勿通过其他渠道支付」；
    - iOS 端虚拟商品不得引导外部支付：由前端按 UA/平台判定隐藏支付入口并仅展示
      权益说明（服务端不下发 iOS 专属分流，阶段一由前端处理）；
    - 本模块为模拟支付：mock-pay 直接置 paid 并写 wx_transaction_id='MOCK'+order_no，
      正式接入微信支付时替换回调签名校验，状态机与幂等语义保持不变。

幂等与状态机（mock-pay）：
    - pending → paid：写 paid_at / wx_transaction_id（状态机单向流转）；
    - 已 paid 订单的**无参重放**视为支付回调重复通知 → 200 幂等返回既有结果；
    - 已 paid 订单携带 simulate 参数（新支付指令）或对 failed/refunded/closed
      订单的任何支付操作 → 422（非 pending 不可流转）；
    - pending + simulate='fail' → status='failed'（仅 pending 可 failed）。

订单号规则：
    order_no = "MO" + 时间戳(14 位) + 6 位随机大写十六进制，UNIQUE 冲突时
    重新生成重试（最多 5 次）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ability.member import get_member_status, get_quota
from app.api.v1.deps import (
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    api_error,
    resolve_user,
)
from app.core.db import get_db
from app.core.logging import get_logger
from app.models import Order, RemoteConfig
from app.schemas.member import (
    MemberMeResponse,
    MemberPlanResponse,
    MockPayRequest,
    OrderCreateRequest,
    OrderListResponse,
)

router = APIRouter(prefix="/member", tags=["会员与支付"])

logger = get_logger(__name__)

# 模拟价目表（单位：分）🔴 模拟价目，小程序阶段按商务定价配置化（迁移 remote_config）
_PRICE_TABLE: dict[str, dict] = {
    "monthly": {
        "name": "月卡",
        "price_cents": 2500,
    },
    "quarterly": {
        "name": "季卡",
        "price_cents": 6800,
    },
    "yearly": {
        "name": "年卡",
        "price_cents": 22800,
    },
}

# 会员权益文案（价目表展示用，PRD §8.9 固定六项）
_PLAN_BENEFITS = [
    "不限次推荐与识别",
    "一周饮食计划自动生成",
    "智能购物清单编排",
    "营养周报",
    "家庭多成员差异化定制",
    "去广告",
]

# 支付渠道标识（小程序虚拟支付，🔴 合规约束见模块头）
_PAY_CHANNEL = "miniprogram_virtual"

# 支付政策提示文案（J.5 合规）
_POLICY_NOTE = "小程序虚拟支付；请勿通过其他渠道支付"

# 支付入口关闭错误码与文案（switch.payment=false 时 POST orders / mock-pay 返回）
_ERR_PAYMENT_CLOSED = "PAYMENT_CLOSED"
_MSG_PAYMENT_CLOSED = "支付入口已关闭"

# 订单号生成最大重试次数（order_no UNIQUE 冲突重试上限）
_ORDER_NO_MAX_RETRY = 5


def _iso(dt: datetime | None) -> str | None:
    """datetime → ISO 8601 字符串（统一 UTC 表示）（函数）。

    说明：
        带时区值统一转 UTC（首次写入的内存 UTC 值与回放时 DB 读出的本地时区值
        表示一致，保证幂等重放的 paid_at 逐字符相等）。

    参数：
        dt：时间（可 None）。

    返回值：
        str | None：ISO 8601 字符串（UTC）或 None。

    异常：
        无。
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.isoformat()


def _payment_switch_on(session: Session) -> bool:
    """读 switch.payment 支付开关（函数）。

    说明：
        每请求直查 remote_config（与 config.get_switches 同语义：行缺省/值非法/
        查询异常均回退 True），保证 60s 内生效且不引入缓存。

    参数：
        session：数据库会话。

    返回值：
        bool：开关状态（缺省 True）。

    异常：
        不抛出（异常回退 True）。
    """
    try:
        value = session.execute(
            select(RemoteConfig.value).where(RemoteConfig.config_key == "switch.payment")
        ).scalar_one_or_none()
        return bool(value) if isinstance(value, bool) else True
    except Exception as exc:  # noqa: BLE001 —— 开关读取失败回退开启
        logger.warning("payment switch read failed: %s", exc)
        return True


def _generate_order_no() -> str:
    """生成订单号（函数）。

    说明：
        "MO" + 时间戳（14 位）+ 6 位随机大写十六进制；随机后缀使碰撞概率
        趋近于零，UNIQUE 冲突时由调用方重试。

    参数：
        无。

    返回值：
        str：形如 MO20261009123456A3F9C2 的订单号（≤40 字符，符合列宽）。

    异常：
        无。
    """
    return f"MO{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


def _order_out(order: Order) -> dict:
    """Order ORM → 响应字典（函数）。

    参数：
        order：订单 ORM 实例。

    返回值：
        dict：OrderOut 结构（时间字段 ISO 8601，附 pay_channel）。

    异常：
        无。
    """
    return {
        "order_no": order.order_no,
        "product_type": order.product_type,
        "amount_cents": int(order.amount_cents),
        "status": order.status,
        "paid_at": _iso(order.paid_at),
        "created_at": _iso(order.created_at),
        "wx_transaction_id": order.wx_transaction_id,
        "pay_channel": _PAY_CHANNEL,
    }


@router.get("/plan", response_model=MemberPlanResponse, summary="会员价目表（预览）")
def get_member_plan(session: Session = Depends(get_db)) -> MemberPlanResponse:
    """价目表端点（函数）。

    说明：
        纯预览（preview_only=true，模拟支付不产生真实扣款）；支付开关关闭时
        仍可浏览价目。

    参数：
        session：请求级数据库会话。

    返回值：
        MemberPlanResponse：套餐列表 + 支付渠道 + 开关状态 + 政策提示。

    异常：
        开关查询异常内部回退 True，不向外抛出。
    """
    plans = [
        {
            "product_type": product_type,
            "name": info["name"],
            "price_cents": info["price_cents"],
            "benefits": list(_PLAN_BENEFITS),
            "preview_only": True,
        }
        for product_type, info in _PRICE_TABLE.items()
    ]
    return MemberPlanResponse(
        plans=plans,
        pay_channel=_PAY_CHANNEL,
        payment_switch_on=_payment_switch_on(session),
        policy_note=_POLICY_NOTE,
    )


@router.get("/me", response_model=MemberMeResponse, summary="我的会员状态与识别额度")
def get_member_me(
    request: Request,
    session: Session = Depends(get_db),
) -> MemberMeResponse:
    """会员状态端点（函数）。

    说明：
        会员判定与额度计算委托 app.ability.member（供 T5 vision 复用同一口径）；
        支付开关关闭仍可查询（已购权益不受影响）。

    参数：
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        MemberMeResponse：{is_member, expire_at?, quota{used,limit,remaining}}。

    异常：
        数据库异常向上抛出（全局处理器兜底）。
    """
    user = resolve_user(session, None, request)
    session.commit()
    status = get_member_status(session, int(user.id))
    quota = get_quota(session, int(user.id))
    return MemberMeResponse(
        is_member=status["is_member"],
        expire_at=status["expire_at"],
        quota=quota,
    )


@router.post("/orders", summary="创建会员订单（模拟支付）", status_code=201)
def create_member_order(
    payload: OrderCreateRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """创建订单端点（函数）。

    说明：
        product_type 非法由 Pydantic Literal 校验为 422；order_no 冲突自动重试；
        支付开关关闭（switch.payment=false）返回 403「支付入口已关闭」。

    参数：
        payload：创建请求体（product_type）。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：201 {order_no, amount_cents, status:'pending', created_at, pay_channel}。

    异常：
        HTTPException 403：支付入口关闭；409 后兜底 500（重试耗尽）；
        IntegrityError 重试后仍冲突向上抛出。
    """
    if not _payment_switch_on(session):
        raise api_error(403, _ERR_PAYMENT_CLOSED, _MSG_PAYMENT_CLOSED)

    user = resolve_user(session, None, request)
    price = _PRICE_TABLE[payload.product_type]["price_cents"]
    for _attempt in range(_ORDER_NO_MAX_RETRY):
        order = Order(
            order_no=_generate_order_no(),
            user_id=int(user.id),
            product_type=payload.product_type,
            amount_cents=price,
            status="pending",
        )
        session.add(order)
        try:
            session.commit()
            return JSONResponse(status_code=201, content=_order_out(order))
        except IntegrityError:
            # order_no UNIQUE 冲突：回滚并重新生成（随机后缀碰撞概率趋近于零）
            session.rollback()
            logger.warning("order_no conflict, retrying (%s)", order.order_no)
    raise api_error(500, "ORDER_NO_EXHAUSTED", "订单号生成失败，请重试")


@router.post("/orders/{order_no}/mock-pay", summary="模拟支付回调（幂等）")
def mock_pay_order(
    order_no: str,
    payload: MockPayRequest | None = None,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """模拟支付回调端点（函数）。

    说明：
        状态机 pending→paid（写 paid_at / wx_transaction_id='MOCK'+order_no）；
        幂等语义：已 paid 订单的**无参重放**返回 200 既有结果；携带 simulate 的
        新支付指令或非 pending 订单的状态流转 → 422；pending+simulate='fail'
        → status='failed'（仅 pending 可 failed）。开关关闭 403。

    参数：
        order_no：路径订单号。
        payload：可选请求体（simulate='fail' 模拟支付失败；缺省为正常支付）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：200 订单状态体（paid/failed）。

    异常：
        HTTPException 404：订单不存在；403：支付入口关闭；
        422：非 pending 订单不可流转。
    """
    if not _payment_switch_on(session):
        raise api_error(403, _ERR_PAYMENT_CLOSED, _MSG_PAYMENT_CLOSED)

    order = session.execute(select(Order).where(Order.order_no == order_no)).scalar_one_or_none()
    if order is None:
        raise api_error(404, ERR_NOT_FOUND, "订单不存在", f"order_no={order_no}")

    simulate = payload.simulate if payload is not None else None

    # 幂等重放：已 paid 且无新支付指令（无 simulate）→ 返回既有结果
    if order.status == "paid" and simulate is None:
        return JSONResponse(content=_order_out(order))

    # 状态机：仅 pending 可流转（paid + simulate / failed / refunded / closed → 422）
    if order.status != "pending":
        raise api_error(
            422,
            ERR_CONFLICT,
            "订单状态不允许支付",
            f"order_no={order_no}, status={order.status}",
        )

    if simulate == "fail":
        # 模拟支付失败（仅 pending 可 failed）
        order.status = "failed"
        session.commit()
        return JSONResponse(content=_order_out(order))

    # 模拟支付成功：pending → paid
    order.status = "paid"
    order.paid_at = datetime.now(UTC)
    order.wx_transaction_id = f"MOCK{order.order_no}"
    session.commit()
    logger.info("mock pay success", extra={"order_no": order.order_no})
    return JSONResponse(content=_order_out(order))


@router.get("/orders", response_model=OrderListResponse, summary="我的订单列表")
def list_member_orders(
    request: Request,
    status: str | None = None,
    session: Session = Depends(get_db),
) -> OrderListResponse:
    """订单列表端点（函数）。

    说明：
        仅返回本人订单，created_at 倒序；status 过滤参数不校验枚举
        （非法值自然过滤为空列表，不抛错）。

    参数：
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        status：可选状态过滤（pending/paid/failed/refunded/closed）。
        session：请求级数据库会话。

    返回值：
        OrderListResponse：{items: [...]}。

    异常：
        数据库异常向上抛出（全局处理器兜底）。
    """
    user = resolve_user(session, None, request)
    session.commit()
    stmt = (
        select(Order)
        .where(Order.user_id == int(user.id))
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if status:
        stmt = stmt.where(Order.status == status)
    orders = session.execute(stmt).scalars().all()
    return OrderListResponse(items=[_order_out(order) for order in orders])
