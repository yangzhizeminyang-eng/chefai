"""会员与支付 Schema 模块（模块 J，模拟支付）。

职责：
    /v1/member/* 的请求与响应模型：
    - GET  /v1/member/plan：价目表（预览）；
    - GET  /v1/member/me：会员状态与识别额度；
    - POST /v1/member/orders：创建待支付订单；
    - POST /v1/member/orders/{order_no}/mock-pay：模拟支付回调；
    - GET  /v1/member/orders：本人订单列表。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 会员套餐类型（order.product_type 业务口径）
ProductType = Literal["monthly", "quarterly", "yearly"]

# 订单状态（对齐 order 表 chk_status CHECK 枚举）
OrderStatus = Literal["pending", "paid", "failed", "refunded", "closed"]


class MemberPlanItem(BaseModel):
    """单个套餐价目项（模型类）。

    属性：
        product_type：套餐类型（monthly/quarterly/yearly）。
        name：套餐名（月卡/季卡/年卡）。
        price_cents：价格（分）。
        benefits：权益文案列表。
        preview_only：是否仅预览（模拟支付阶段恒 true，不产生真实扣款）。
    """

    product_type: ProductType
    name: str
    price_cents: int
    benefits: list[str] = Field(default_factory=list)
    preview_only: bool = True


class MemberPlanResponse(BaseModel):
    """价目表响应体（模型类）。

    说明：
        开关关闭时仍可访问（浏览价目不受支付入口关闭影响）。

    属性：
        plans：套餐列表（月/季/年）。
        pay_channel：支付渠道标识（小程序虚拟支付）。
        payment_switch_on：支付开关状态（switch.payment）。
        policy_note：支付政策提示文案。
    """

    plans: list[MemberPlanItem] = Field(default_factory=list)
    pay_channel: str = "miniprogram_virtual"
    payment_switch_on: bool = True
    policy_note: str = ""


class MemberQuotaOut(BaseModel):
    """识别额度（模型类）。

    属性：
        used：当日已用次数。
        limit：当日总额度（会员 10 / 免费 3）。
        remaining：当日剩余次数。
    """

    used: int = 0
    limit: int = 3
    remaining: int = 3


class MemberMeResponse(BaseModel):
    """会员状态响应体（模型类）。

    说明：
        开关关闭时仍可查询（已购权益不受支付入口关闭影响）。

    属性：
        is_member：是否有效会员（存在未过期的 paid 订单）。
        expire_at：会员到期时间（ISO 8601；无购买记录为 None）。
        quota：当日 AI 识别额度。
    """

    is_member: bool = False
    expire_at: str | None = None
    quota: MemberQuotaOut = Field(default_factory=MemberQuotaOut)


class OrderCreateRequest(BaseModel):
    """创建订单请求体（模型类）。

    属性：
        product_type：套餐类型（非法值由 Pydantic 校验为 422）。
    """

    product_type: ProductType


class OrderOut(BaseModel):
    """订单响应体（模型类）。

    属性：
        order_no：订单号（MO 前缀，唯一）。
        product_type：套餐类型。
        amount_cents：金额（分）。
        status：订单状态。
        paid_at：支付时间（ISO 8601 UTC，未支付为 None）。
        created_at：创建时间（ISO 8601 UTC）。
        wx_transaction_id：模拟交易凭证（'MOCK'+order_no，未支付为 None）。
        pay_channel：支付渠道标识。
        simulated：是否模拟支付通道结果（阶段一恒 true，显式标记模拟通道，
            区别于真实微信支付接入后的 false；新增可选字段，前端可忽略）。
    """

    order_no: str
    product_type: str
    amount_cents: int
    status: str
    paid_at: str | None = None
    created_at: str | None = None
    wx_transaction_id: str | None = None
    pay_channel: str = "miniprogram_virtual"
    simulated: bool = True


class MockPayRequest(BaseModel):
    """模拟支付回调请求体（模型类）。

    说明：
        可整体缺省（缺省 = 正常支付成功回调）；
        simulate='fail' 为模拟支付失败场景（仅 pending 订单可流转为 failed）。

    属性：
        simulate：模拟场景（当前仅支持 'fail'；None 表示正常支付）。
    """

    simulate: Literal["fail"] | None = None


class OrderListResponse(BaseModel):
    """订单列表响应体（模型类）。

    属性：
        items：本人订单（created_at 倒序）。
    """

    items: list[OrderOut] = Field(default_factory=list)
