"""支付能力适配器模块（provider 模式，模块 J 支付接线）。

职责：
    定义支付提供方抽象接口及各实现，供 /v1/member/* 支付路径统一消费：
    - PaymentResult：支付操作结果（success / transaction_id / simulated / message）；
    - PaymentProvider：抽象接口（pay / query / refund，按现有 mock 最小语义）；
    - MockPaymentProvider：模拟支付实现——沿用模块 J 既有 mock 语义（交易凭证
      'MOCK'+order_no、simulate='fail' 失败路径、同参幂等重放同结果），所有
      结果携带 simulated=True 标记（模拟通道显式可辨识，前端与审计可区分）；
    - WechatPayProvider：真实微信支付占位骨架——🔴 未实现（无商户凭证，
      待商户号/APIv3 密钥/沙箱环境验证后实现），方法恒抛 NotImplementedError，
      仅锁定接口形状防误用；
    - get_payment_provider()：工厂——读 PAYMENT_PROVIDER（进程环境变量，
      缺省 'mock'）；配置未指向可用真实 provider（未知名 / 'wechat' 未实现）
      时回退 mock 并 logger.warning，绝不伪装成真实渠道。

🔴 真实微信支付接入状态（待环境验证，本阶段不实现）：
    需要商户凭证（商户号 mch_id、APIv3 密钥、商户证书序列号、平台证书/回调
    验签公钥）与微信支付沙箱环境联调；实现时在 WechatPayProvider 中补齐
    下单（JSAPI/小程序统一下单）、回调验签（Wechatpay-Signature）、退款
    证书调用，并将支付入口开关（switch.payment）与渠道标注同步切换为真实
    渠道口径。接入前任何请求不得触发真实扣款。

配置说明：
    config.py 由并行任务持有（禁改），支付配置暂以进程环境变量
    PAYMENT_PROVIDER + 本模块常量实现（缺省 'mock'）；真实微信支付接入时
    迁移至 Settings（PAYMENT_PROVIDER / PAYMENT_MCH_ID / PAYMENT_API_V3_KEY
    等字段），风格对齐 providers.py 的 VISION_PROVIDER / SPEECH_PROVIDER。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

# 支付 provider 配置环境变量名（进程环境变量；.env 值不注入 os.environ，
# 服务进程需在启动环境显式设置——缺省恒为 mock，与「阶段一模拟支付」一致）
_PROVIDER_ENV_KEY = "PAYMENT_PROVIDER"

# 缺省 provider 名（未配置时回退模拟支付）
_DEFAULT_PROVIDER = "mock"

# 已注册的真实渠道名（当前仅 'wechat' 占位；未实现，工厂遇之回退 mock）
_REAL_PROVIDER_NAMES: frozenset[str] = frozenset({"wechat"})


@dataclass
class PaymentResult:
    """单次支付操作结果（模型类）。

    属性：
        success：操作是否成功（支付成功 / 查询到已支付 / 退款受理成功）。
        transaction_id：渠道交易凭证（模拟通道为 'MOCK'+order_no；
            查询未支付 / 支付失败时为 None）。
        simulated：是否模拟通道结果（模拟实现恒 True；真实渠道恒 False，
            供前端与审计显式区分，杜绝把模拟结果当真实扣款）。
        message：附加说明（失败原因 / 查询状态描述，可空串）。
    """

    success: bool
    transaction_id: str | None = None
    simulated: bool = False
    message: str = ""


class PaymentProvider(ABC):
    """支付提供方抽象接口（抽象类）。

    说明：
        按模块 J 现有 mock 最小语义定义三方法：pay（支付回调受理）、
        query（订单支付状态查询）、refund（退款受理）。阶段一仅
        MockPaymentProvider 实现；真实微信支付经 WechatPayProvider 落位。

    异常：
        实现方对非法入参（如金额篡改）抛 ValueError；真实渠道网络/验签
        异常由实现方包装后抛出，调用方（路由层）映射为 4xx/5xx。
    """

    @abstractmethod
    def pay(self, order_no: str, amount_cents: int, simulate: str | None = None) -> PaymentResult:
        """受理支付（抽象方法）。

        参数：
            order_no：订单号（幂等键：同参重复调用须返回同结果）。
            amount_cents：支付金额（分，必须为正整数；篡改/非法值拒绝）。
            simulate：模拟场景指令（mock 通道支持 'fail' 模拟支付失败；
                真实渠道忽略或拒绝该参数）。

        返回值：
            PaymentResult：支付结果（success=False 表示支付失败路径）。

        异常：
            ValueError：金额非法（非正整数 / bool / 非整数类型）。
        """
        raise NotImplementedError

    @abstractmethod
    def query(self, order_no: str, transaction_id: str | None = None) -> PaymentResult:
        """查询订单支付状态（抽象方法）。

        参数：
            order_no：订单号。
            transaction_id：已知渠道交易凭证（有值且有效 → 已支付）。

        返回值：
            PaymentResult：success=True 表示已支付；False 表示未支付/查询不到。

        异常：
            实现方定义（真实渠道网络异常包装后抛出）。
        """
        raise NotImplementedError

    @abstractmethod
    def refund(self, order_no: str, amount_cents: int, transaction_id: str | None = None) -> PaymentResult:
        """受理退款（抽象方法）。

        参数：
            order_no：订单号。
            amount_cents：退款金额（分，必须为正整数）。
            transaction_id：原支付交易凭证（真实渠道必填，mock 可省）。

        返回值：
            PaymentResult：退款受理结果。

        异常：
            ValueError：金额非法；真实渠道网络异常包装后抛出。
        """
        raise NotImplementedError


def _validate_amount(order_no: str, amount_cents: int) -> None:
    """校验支付金额合法性（内部纯函数）。

    说明：
        金额篡改拒绝接缝：必须为 int 且为正（bool 是 int 子类需显式拒绝，
        防 True 被当作 1）；非法值抛 ValueError，由端点层映射 422。

    参数：
        order_no：订单号（仅用于异常消息定位）。
        amount_cents：待校验金额（分）。

    返回值：
        None。

    异常：
        ValueError：非 int / bool / ≤0 时抛出。
    """
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValueError(f"非法支付金额（须为正整数分）: order_no={order_no}, amount={amount_cents!r}")


class MockPaymentProvider(PaymentProvider):
    """模拟支付实现（模型类，模块 J 既有 mock 语义）。

    说明：
        无状态纯函数式实现（幂等由「同参同结果」保证）：pay 成功返回
        'MOCK'+order_no 交易凭证，simulate='fail' 返回失败路径；query 按
        是否持有凭证判定；refund 返回 'MOCK-REFUND'+order_no 退款凭证。
        所有结果 simulated=True（模拟通道显式标记）。金额非法抛 ValueError。

    属性：
        mode：通道标识（恒 'mock'，与 ASR/Vision/TTS provider 的 mode
            标记口径一致，响应层透出供辨识）。
    """

    mode = "mock"

    def pay(self, order_no: str, amount_cents: int, simulate: str | None = None) -> PaymentResult:
        """受理模拟支付（函数）。

        参数：
            order_no：订单号。
            amount_cents：支付金额（分，正整数）。
            simulate：'fail' 模拟支付失败；None 正常支付。

        返回值：
            PaymentResult：成功 → (True, 'MOCK'+order_no, simulated=True)；
                失败 → (False, None, simulated=True)。

        异常：
            ValueError：金额非法。
        """
        _validate_amount(order_no, amount_cents)
        if simulate == "fail":
            return PaymentResult(
                success=False, transaction_id=None, simulated=True, message="模拟支付失败",
            )
        return PaymentResult(
            success=True, transaction_id=f"MOCK{order_no}", simulated=True, message="模拟支付成功",
        )

    def query(self, order_no: str, transaction_id: str | None = None) -> PaymentResult:
        """查询模拟支付状态（函数）。

        参数：
            order_no：订单号。
            transaction_id：渠道交易凭证（mock 通道有值即视为已支付）。

        返回值：
            PaymentResult：已支付 → (True, transaction_id, simulated=True)；
                未支付 → (False, None, simulated=True)。

        异常：
            无。
        """
        if transaction_id:
            return PaymentResult(
                success=True, transaction_id=transaction_id, simulated=True, message="已支付（模拟查询）",
            )
        return PaymentResult(
            success=False, transaction_id=None, simulated=True, message="未支付（模拟查询）",
        )

    def refund(self, order_no: str, amount_cents: int, transaction_id: str | None = None) -> PaymentResult:
        """受理模拟退款（函数）。

        参数：
            order_no：订单号。
            amount_cents：退款金额（分，正整数）。
            transaction_id：原支付交易凭证（mock 通道忽略）。

        返回值：
            PaymentResult：(True, 'MOCK-REFUND'+order_no, simulated=True)。

        异常：
            ValueError：金额非法。
        """
        _validate_amount(order_no, amount_cents)
        return PaymentResult(
            success=True, transaction_id=f"MOCK-REFUND{order_no}", simulated=True, message="模拟退款成功",
        )


class WechatPayProvider(PaymentProvider):
    """真实微信支付占位骨架（模型类）。

    🔴 接入状态：未实现——无商户凭证（商户号 / APIv3 密钥 / 商户证书），
    待微信支付沙箱环境验证后按官方 APIv3 协议实现（统一下单、回调验签、
    退款）；实现前工厂对该渠道回退 mock 并 warning，绝不以 mock 结果
    冒充真实渠道扣款。

    属性：
        mode：通道标识（'wechat'，真实渠道接入后响应层据此辨识）。
    """

    mode = "wechat"

    def pay(self, order_no: str, amount_cents: int, simulate: str | None = None) -> PaymentResult:
        """受理微信支付（占位，待商户凭证/沙箱环境验证）（函数）。

        参数：
            order_no：订单号。
            amount_cents：支付金额（分）。
            simulate：模拟指令（真实渠道不适用）。

        返回值：
            无（恒抛出）。

        异常：
            NotImplementedError：真实微信支付未实现（待环境验证）。
        """
        raise NotImplementedError("真实微信支付待商户凭证/沙箱环境验证后实现（见 payment.py 模块文档）")

    def query(self, order_no: str, transaction_id: str | None = None) -> PaymentResult:
        """查询微信支付状态（占位，待环境验证）（函数）。

        参数：
            order_no：订单号。
            transaction_id：渠道交易凭证。

        返回值：
            无（恒抛出）。

        异常：
            NotImplementedError：真实微信支付未实现。
        """
        raise NotImplementedError("真实微信支付待商户凭证/沙箱环境验证后实现（见 payment.py 模块文档）")

    def refund(self, order_no: str, amount_cents: int, transaction_id: str | None = None) -> PaymentResult:
        """受理微信退款（占位，待环境验证）（函数）。

        参数：
            order_no：订单号。
            amount_cents：退款金额（分）。
            transaction_id：原支付交易凭证。

        返回值：
            无（恒抛出）。

        异常：
            NotImplementedError：真实微信支付未实现。
        """
        raise NotImplementedError("真实微信支付待商户凭证/沙箱环境验证后实现（见 payment.py 模块文档）")


def get_payment_provider() -> PaymentProvider:
    """支付 provider 工厂（函数）。

    说明：
        读进程环境变量 PAYMENT_PROVIDER（缺省 'mock'）：'mock' → 模拟实现；
        'wechat' → 真实微信支付**未实现/未验证**，warning 后回退 mock（绝不
        以 mock 结果冒充真实渠道）；未知名 → warning 回退 mock。阶段一
        mock provider 无状态、构造零成本，不做进程级单例缓存；真实渠道
        接入时再加缓存（参照 providers.py 的加锁单例模式）。

    返回值：
        PaymentProvider：支付 provider 实例（当前恒为 MockPaymentProvider）。

    异常：
        不抛出（任何配置异常回退 mock 并 warning）。
    """
    name = (os.getenv(_PROVIDER_ENV_KEY, "") or "").strip().lower() or _DEFAULT_PROVIDER
    if name == "mock":
        return MockPaymentProvider()
    if name in _REAL_PROVIDER_NAMES:
        # 'wechat' 占位已存在但未实现/未验证：回退 mock，warning 显式声明
        logger.warning(
            "PAYMENT_PROVIDER=%s 为真实渠道但尚未实现/未验证（待商户凭证与沙箱环境），回退 mock",
            name,
        )
        return MockPaymentProvider()
    logger.warning("未知的 PAYMENT_PROVIDER=%s，回退 mock", name)
    return MockPaymentProvider()


__all__ = [
    "PaymentResult",
    "PaymentProvider",
    "MockPaymentProvider",
    "WechatPayProvider",
    "get_payment_provider",
]
