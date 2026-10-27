"""支付 provider 抽象与模拟标记测试（任务 A，TDD）。

覆盖：
    - simulated 标记：下单 / mock-pay（成功与失败路径）/ 幂等重放 / 订单列表
      响应体均携带 "simulated": true（模拟支付通道显式标记，前端可辨识）；
    - MockPaymentProvider 状态机：pending→paid（MOCK+order_no 交易号、simulated=true）、
      simulate='fail'→success=False、同参重复调用幂等返回同结果（重复回调语义）；
    - 金额篡改拒绝：amount_cents ≤ 0 / 非整数（含 bool）→ ValueError；
      端点级接缝：DB 中金额被篡改为 0 的 pending 订单支付 → 422；
    - 工厂降级：未配置 → mock；未知名 → mock + warning；'wechat'（未实现）
      → mock + warning；WechatPayProvider 占位契约（NotImplementedError）；
    - query / refund 最小语义（模拟通道恒 simulated=true）。

说明：
    switch.payment=false 关闭入口行为由既有 tests/test_api_member.py::
    test_payment_switch_off_blocks_post_but_keeps_get 覆盖（复跑确认，不重复）。

清理约定：
    自建唯一后缀匿名用户及其订单，禁删种子数据。
"""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.ability.payment import (
    MockPaymentProvider,
    PaymentProvider,
    WechatPayProvider,
    get_payment_provider,
)
from app.core.db import SessionLocal
from app.models import Order, User


def _unique_anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：anon_paytest_ 前缀唯一串。

    异常：
        无。
    """
    return f"anon_paytest_{uuid.uuid4().hex[:12]}"


def _delete_user_with_orders(anon_id: str) -> None:
    """清理测试用户及其订单（函数）。

    说明：
        order.user_id 外键无级联，先删订单再删用户；仅删自建数据，禁删种子。

    参数：
        anon_id：匿名 ID。

    返回值：
        None。

    异常：
        数据库异常向上抛出（清理失败即测试失败，避免脏数据残留）。
    """
    with SessionLocal() as session:
        user = session.execute(
            select(User).where(User.anonymous_id == anon_id)
        ).scalar_one_or_none()
        if user is None:
            return
        uid = int(user.id)
        session.execute(delete(Order).where(Order.user_id == uid))
        session.execute(delete(User).where(User.id == uid))
        session.commit()


def _create_order(client: TestClient, anon: str, product_type: str = "monthly") -> dict:
    """创建待支付订单（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名 ID（请求头）。
        product_type：套餐类型。

    返回值：
        dict：订单响应体。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/member/orders", json={"product_type": product_type},
        headers={"X-Anonymous-Id": anon},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# simulated 标记（响应契约）
# ---------------------------------------------------------------------------
def test_create_order_response_has_simulated_flag(client: TestClient) -> None:
    """下单响应携带 simulated=true（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        order = _create_order(client, anon, "monthly")
        assert order["simulated"] is True
    finally:
        _delete_user_with_orders(anon)


def test_mock_pay_response_has_simulated_flag(client: TestClient) -> None:
    """mock-pay 成功与失败路径响应均携带 simulated=true（函数）。

    说明：
        simulated 标记表示「模拟支付通道」（区别于真实微信支付），
        与支付是否成功无关，failed 路径同样标记。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        order_ok = _create_order(client, anon, "monthly")
        paid = client.post(f"/v1/member/orders/{order_ok['order_no']}/mock-pay")
        assert paid.status_code == 200
        assert paid.json()["simulated"] is True
        assert paid.json()["status"] == "paid"

        order_fail = _create_order(client, anon, "yearly")
        failed = client.post(
            f"/v1/member/orders/{order_fail['order_no']}/mock-pay",
            json={"simulate": "fail"},
        )
        assert failed.status_code == 200
        assert failed.json()["simulated"] is True
        assert failed.json()["status"] == "failed"
    finally:
        _delete_user_with_orders(anon)


def test_mock_pay_replay_simulated_flag_stable(client: TestClient) -> None:
    """幂等重放响应携带相同 simulated 标记与既有结果（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        order = _create_order(client, anon, "quarterly")
        first = client.post(f"/v1/member/orders/{order['order_no']}/mock-pay").json()
        second = client.post(f"/v1/member/orders/{order['order_no']}/mock-pay").json()
        assert second["simulated"] is True
        assert second["paid_at"] == first["paid_at"]
        assert second["wx_transaction_id"] == first["wx_transaction_id"]
    finally:
        _delete_user_with_orders(anon)


def test_order_list_carries_simulated_flag(client: TestClient) -> None:
    """订单列表（response_model 过滤路径）同样携带 simulated 标记（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        _create_order(client, anon, "monthly")
        items = client.get(
            "/v1/member/orders", headers={"X-Anonymous-Id": anon}
        ).json()["items"]
        assert len(items) == 1
        assert items[0]["simulated"] is True
    finally:
        _delete_user_with_orders(anon)


# ---------------------------------------------------------------------------
# MockPaymentProvider 状态机与幂等
# ---------------------------------------------------------------------------
def test_mock_provider_pay_success_state_transition() -> None:
    """pay 成功语义：MOCK+order_no 交易号 + simulated=true（函数）。

    说明：
        对应端点层 pending→paid 状态机的 provider 侧语义：pending 订单经
        provider.pay 返回 success=True 与 'MOCK'+order_no 交易凭证。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    provider = MockPaymentProvider()
    assert isinstance(provider, PaymentProvider)
    result = provider.pay("MO20260101000000AAA", 2500)
    assert result.success is True
    assert result.simulated is True
    assert result.transaction_id == "MOCKMO20260101000000AAA"


def test_mock_provider_pay_simulate_fail() -> None:
    """simulate='fail' → success=False（对应 pending→failed，函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    result = MockPaymentProvider().pay("MO20260101000000BBB", 2500, simulate="fail")
    assert result.success is False
    assert result.transaction_id is None
    assert result.simulated is True


def test_mock_provider_pay_idempotent_replay() -> None:
    """同参重复 pay 幂等返回同结果（重复回调语义，函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    provider = MockPaymentProvider()
    first = provider.pay("MO20260101000000CCC", 6800)
    second = provider.pay("MO20260101000000CCC", 6800)
    assert (first.success, first.transaction_id, first.simulated) == (
        second.success, second.transaction_id, second.simulated,
    )


def test_mock_provider_query_refund_semantics() -> None:
    """query/refund 最小语义：模拟通道恒 simulated=true（函数）。

    说明：
        query 无交易凭证 → success=False（未支付）；有凭证 → success=True；
        refund 返回 MOCK-REFUND 前缀退款凭证。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    provider = MockPaymentProvider()
    unpaid = provider.query("MO20260101000000DDD")
    assert unpaid.success is False
    assert unpaid.simulated is True
    paid = provider.query("MO20260101000000DDD", transaction_id="MOCKMO20260101000000DDD")
    assert paid.success is True
    assert paid.simulated is True

    refunded = provider.refund("MO20260101000000DDD", 2500)
    assert refunded.success is True
    assert refunded.simulated is True
    assert refunded.transaction_id == "MOCK-REFUNDMO20260101000000DDD"


# ---------------------------------------------------------------------------
# 金额篡改拒绝
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_amount", [0, -1, -2500, 25.5, "2500", True])
def test_mock_provider_rejects_invalid_amount(bad_amount) -> None:
    """非法金额（≤0 / 非整数 / bool）→ ValueError（函数）。

    参数：
        bad_amount：非法金额样本（parametrize）。

    返回值：
        None。

    异常：
        未抛 ValueError 即测试失败。
    """
    with pytest.raises(ValueError):
        MockPaymentProvider().pay("MO20260101000000EEE", bad_amount)


def test_mock_pay_tampered_amount_rejected_422(client: TestClient) -> None:
    """端点接缝：订单金额被篡改为 0 → mock-pay 422（函数）。

    说明：
        模拟攻击者直改 DB 金额后发起支付：provider 金额校验拒绝，
        端点层映射为 422（PAYMENT_AMOUNT_INVALID），订单保持 pending。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        headers = {"X-Anonymous-Id": anon}
        resp = client.post(
            "/v1/member/orders", json={"product_type": "monthly"}, headers=headers
        )
        assert resp.status_code == 201
        order_no = resp.json()["order_no"]
        # 模拟金额篡改（绕过价目表直改 DB）
        with SessionLocal() as session:
            order = session.execute(
                select(Order).where(Order.order_no == order_no)
            ).scalar_one()
            order.amount_cents = 0
            session.commit()
        pay_resp = client.post(f"/v1/member/orders/{order_no}/mock-pay")
        assert pay_resp.status_code == 422
        assert pay_resp.json()["code"] == "PAYMENT_AMOUNT_INVALID"
        # 订单保持 pending（未发生状态流转）
        with SessionLocal() as session:
            order = session.execute(
                select(Order).where(Order.order_no == order_no)
            ).scalar_one()
            assert order.status == "pending"
    finally:
        _delete_user_with_orders(anon)


# ---------------------------------------------------------------------------
# 工厂降级与占位契约
# ---------------------------------------------------------------------------
def test_factory_default_returns_mock() -> None:
    """未配置 PAYMENT_PROVIDER → 缺省 mock 实例（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    provider = get_payment_provider()
    assert isinstance(provider, MockPaymentProvider)
    assert provider.pay("MOX", 1).simulated is True


def test_factory_unknown_name_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """未知 PAYMENT_PROVIDER 名 → 回退 mock 且记 warning（函数）。

    参数：
        monkeypatch：设置进程环境变量 PAYMENT_PROVIDER。
        caplog：捕获 payment 模块日志。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setenv("PAYMENT_PROVIDER", "alipay-unknown")
    with caplog.at_level(logging.WARNING, logger="app.ability.payment"):
        provider = get_payment_provider()
    assert isinstance(provider, MockPaymentProvider)
    assert any("PAYMENT_PROVIDER" in record.message for record in caplog.records)


def test_factory_wechat_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """PAYMENT_PROVIDER='wechat'（真实渠道未实现）→ 回退 mock + warning（函数）。

    参数：
        monkeypatch：设置进程环境变量 PAYMENT_PROVIDER。
        caplog：捕获 payment 模块日志。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setenv("PAYMENT_PROVIDER", "wechat")
    with caplog.at_level(logging.WARNING, logger="app.ability.payment"):
        provider = get_payment_provider()
    assert isinstance(provider, MockPaymentProvider)
    assert any("wechat" in record.message.lower() for record in caplog.records)


def test_wechat_provider_is_placeholder() -> None:
    """WechatPayProvider 占位契约：三方法均 NotImplementedError（函数）。

    说明：
        真实微信支付待商户凭证/沙箱环境验证后实现；占位类仅锁定接口形状，
        防止误把未验证通道当作可用实现。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    provider = WechatPayProvider()
    assert isinstance(provider, PaymentProvider)
    with pytest.raises(NotImplementedError):
        provider.pay("MOX", 1)
    with pytest.raises(NotImplementedError):
        provider.query("MOX")
    with pytest.raises(NotImplementedError):
        provider.refund("MOX", 1)


def test_pay_response_channel_remains_virtual(client: TestClient) -> None:
    """接线后支付渠道仍为 miniprogram_virtual（合规口径不变，函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        order = _create_order(client, anon, "monthly")
        assert order["pay_channel"] == "miniprogram_virtual"
        paid = client.post(f"/v1/member/orders/{order['order_no']}/mock-pay").json()
        assert paid["pay_channel"] == "miniprogram_virtual"
        assert paid["wx_transaction_id"] == f"MOCK{order['order_no']}"
    finally:
        _delete_user_with_orders(anon)
