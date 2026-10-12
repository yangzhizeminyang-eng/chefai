"""会员与支付接口集成测试（模块 J，模拟支付）。

覆盖（spec Task 4 模块 J）：
    - GET /v1/member/plan 价目表结构（三档价格/权益/渠道/开关/政策提示）；
    - POST /v1/member/orders 创建订单（order_no 唯一、非法 product_type 422）；
    - POST mock-pay：成功 paid_at/wx_transaction_id 写入、重复支付幂等 200、
      paid 订单携带 simulate 再支付 422、simulate='fail'→failed、非 pending 支付 422；
    - GET /v1/member/me 会员判定（paid 后 is_member=true、额度 limit 4→10）；
    - GET /v1/member/orders 列表与 status 过滤；
    - switch.payment=false：POST orders / mock-pay 403「支付入口已关闭」，GET 正常；
    - ability.member 额度函数单测（consume/refund/跨日重置/超额 ValueError）。

清理约定：
    自建唯一后缀匿名用户及其订单，remote_config 改动 try/finally 还原，禁删种子。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.ability.member import consume_quota, get_member_status, get_quota, refund_quota
from app.api.v1 import member as member_api
from app.core.db import SessionLocal
from app.main import app as main_app
from app.models import Order, RemoteConfig, User


def _ensure_routes_registered() -> None:
    """并行开发兜底：router.py 由其他任务负责注册（函数）。

    说明：
        router.py 属禁改文件；若其他任务尚未注册本模块路由，则在主应用上
        幂等挂载（已注册则跳过），保证本测试模块可独立运行。

    参数：
        无。

    返回值：
        None。

    异常：
        无。
    """
    paths = {getattr(route, "path", "") for route in main_app.routes}
    if "/v1/member/plan" not in paths:
        main_app.include_router(member_api.router, prefix="/v1")


_ensure_routes_registered()


def _unique_anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：anon_test_ 前缀唯一串。

    异常：
        无。
    """
    return f"anon_test_{uuid.uuid4().hex[:12]}"


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


def test_member_plan_structure(client: TestClient) -> None:
    """价目表结构（函数）。

    说明：
        三档价格 2500/6800/22800 分；权益六项（PRD §8.9）；preview_only=true；
        渠道 miniprogram_virtual；政策提示非空。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/member/plan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pay_channel"] == "miniprogram_virtual"
    assert body["payment_switch_on"] is True
    assert body["policy_note"]
    assert len(body["plans"]) == 3
    expected_prices = {"monthly": 2500, "quarterly": 6800, "yearly": 22800}
    expected_names = {"monthly": "月卡", "quarterly": "季卡", "yearly": "年卡"}
    for plan in body["plans"]:
        assert plan["price_cents"] == expected_prices[plan["product_type"]]
        assert plan["name"] == expected_names[plan["product_type"]]
        assert plan["benefits"] == [
            "不限次推荐与识别",
            "一周饮食计划自动生成",
            "智能购物清单编排",
            "营养周报",
            "家庭多成员差异化定制",
            "去广告",
        ]
        assert plan["preview_only"] is True


def test_create_order_and_unique_order_no(client: TestClient) -> None:
    """创建订单 + order_no 唯一（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        first = _create_order(client, anon, "monthly")
        second = _create_order(client, anon, "yearly")
        assert first["order_no"].startswith("MO")
        assert second["order_no"].startswith("MO")
        assert first["order_no"] != second["order_no"]
        assert first["amount_cents"] == 2500
        assert second["amount_cents"] == 22800
        for order in (first, second):
            assert order["status"] == "pending"
            assert order["paid_at"] is None
            assert order["created_at"]
            assert order["pay_channel"] == "miniprogram_virtual"
    finally:
        _delete_user_with_orders(anon)


def test_create_order_invalid_product_type_422(client: TestClient) -> None:
    """非法 product_type → 422（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/member/orders", json={"product_type": "weekly"},
        headers={"X-Anonymous-Id": _unique_anon()},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_mock_pay_success_and_member_status(client: TestClient) -> None:
    """mock-pay 成功：paid_at 写入 + is_member 判定 + 额度 limit 3→10（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        # 支付前：非会员，免费额度 3
        me_before = client.get("/v1/member/me", headers={"X-Anonymous-Id": anon}).json()
        assert me_before["is_member"] is False
        assert me_before["quota"]["limit"] == 3

        order = _create_order(client, anon, "monthly")
        resp = client.post(
            f"/v1/member/orders/{order['order_no']}/mock-pay",
            headers={"X-Anonymous-Id": anon},
        )
        assert resp.status_code == 200
        paid = resp.json()
        assert paid["status"] == "paid"
        assert paid["paid_at"]
        assert paid["wx_transaction_id"] == f"MOCK{order['order_no']}"

        # 支付后：会员，额度 limit 10，到期时间非空
        me_after = client.get("/v1/member/me", headers={"X-Anonymous-Id": anon}).json()
        assert me_after["is_member"] is True
        assert me_after["expire_at"]
        assert me_after["quota"]["limit"] == 10
        assert me_after["quota"]["remaining"] == 10
    finally:
        _delete_user_with_orders(anon)


def test_mock_pay_replay_idempotent(client: TestClient) -> None:
    """重复 mock-pay（无参重放）幂等返回既有结果（函数）。

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
        first = client.post(f"/v1/member/orders/{order['order_no']}/mock-pay")
        assert first.status_code == 200
        second = client.post(f"/v1/member/orders/{order['order_no']}/mock-pay")
        assert second.status_code == 200
        assert second.json()["status"] == "paid"
        # 幂等：paid_at 与首次一致（不重复写）
        assert second.json()["paid_at"] == first.json()["paid_at"]
    finally:
        _delete_user_with_orders(anon)


def test_mock_pay_paid_with_simulate_422(client: TestClient) -> None:
    """对 paid 订单携带 simulate 再支付 → 422（函数）。

    说明：
        已 paid 订单的无参重放是幂等回调；携带 simulate='fail' 视为新的
        状态流转指令，非 pending 一律 422。

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
        assert client.post(f"/v1/member/orders/{order['order_no']}/mock-pay").status_code == 200
        resp = client.post(
            f"/v1/member/orders/{order['order_no']}/mock-pay", json={"simulate": "fail"}
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "STATE_CONFLICT"
    finally:
        _delete_user_with_orders(anon)


def test_mock_pay_simulate_fail_then_repay_422(client: TestClient) -> None:
    """simulate='fail' → failed；对非 pending（failed）订单再支付 → 422（函数）。

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
        resp = client.post(
            f"/v1/member/orders/{order['order_no']}/mock-pay", json={"simulate": "fail"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        assert resp.json()["paid_at"] is None

        # 非 pending（failed）订单再支付 → 422
        repay = client.post(f"/v1/member/orders/{order['order_no']}/mock-pay")
        assert repay.status_code == 422
    finally:
        _delete_user_with_orders(anon)


def test_mock_pay_not_found_404(client: TestClient) -> None:
    """不存在订单 mock-pay → 404（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post("/v1/member/orders/MO99999999999999AA/mock-pay")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_order_list_and_status_filter(client: TestClient) -> None:
    """订单列表倒序 + status 过滤（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        paid_order = _create_order(client, anon, "monthly")
        failed_order = _create_order(client, anon, "yearly")
        client.post(f"/v1/member/orders/{paid_order['order_no']}/mock-pay")
        client.post(
            f"/v1/member/orders/{failed_order['order_no']}/mock-pay",
            json={"simulate": "fail"},
        )

        all_items = client.get(
            "/v1/member/orders", headers={"X-Anonymous-Id": anon}
        ).json()["items"]
        assert len(all_items) == 2
        # created_at 倒序（最新在前）：failed_order 晚创建
        assert all_items[0]["order_no"] == failed_order["order_no"]

        paid_items = client.get(
            "/v1/member/orders", params={"status": "paid"},
            headers={"X-Anonymous-Id": anon},
        ).json()["items"]
        assert [item["order_no"] for item in paid_items] == [paid_order["order_no"]]

        # 他人订单不可见（列表仅本人）
        other = client.get("/v1/member/orders", headers={"X-Anonymous-Id": _unique_anon()})
        assert other.status_code == 200
        assert other.json()["items"] == []
    finally:
        _delete_user_with_orders(anon)


def test_payment_switch_off_blocks_post_but_keeps_get(client: TestClient) -> None:
    """switch.payment=false：POST 403「支付入口已关闭」，GET plan/me 正常（函数）。

    说明：
        直接改 remote_config 行再 try/finally 还原（不污染种子）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（还原逻辑在 finally 中执行）。
    """
    anon = _unique_anon()
    with SessionLocal() as session:
        row = session.execute(
            select(RemoteConfig).where(RemoteConfig.config_key == "switch.payment")
        ).scalar_one()
        original_value = row.value
        row.value = False
        session.commit()
    try:
        # 下单与支付均被关闭
        resp_create = client.post(
            "/v1/member/orders", json={"product_type": "monthly"},
            headers={"X-Anonymous-Id": anon},
        )
        assert resp_create.status_code == 403
        assert resp_create.json()["code"] == "PAYMENT_CLOSED"
        assert resp_create.json()["message"] == "支付入口已关闭"

        resp_pay = client.post("/v1/member/orders/MO99999999999999BB/mock-pay")
        assert resp_pay.status_code == 403
        assert resp_pay.json()["message"] == "支付入口已关闭"

        # 浏览价目与已购权益查询不受影响
        assert client.get("/v1/member/plan").status_code == 200
        me = client.get("/v1/member/me", headers={"X-Anonymous-Id": anon})
        assert me.status_code == 200
        assert me.json()["is_member"] is False

        # 价目表开关字段联动为关闭
        plan = client.get("/v1/member/plan").json()
        assert plan["payment_switch_on"] is False
    finally:
        with SessionLocal() as session:
            row = session.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == "switch.payment")
            ).scalar_one()
            row.value = original_value
            session.commit()
        _delete_user_with_orders(anon)


def test_quota_consume_refund_functions() -> None:
    """额度函数单测：consume/refund/跨日重置/超额 ValueError（函数）。

    说明：
        直接调用 app.ability.member 服务函数（T5 vision 将按此签名集成）：
        - get_quota：免费档 limit=3；
        - consume_quota：used 递增、remaining 递减、超额抛 ValueError；
        - refund_quota：used 回补（下限 0）；
        - 跨日重置：preferences 中 date 非当日 → used 归零。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败或数据库异常即测试失败。
    """
    anon = _unique_anon()
    try:
        with SessionLocal() as session:
            user = User(anonymous_id=anon)
            session.add(user)
            session.commit()
            uid = int(user.id)

        # 初始额度：免费档 3/日
        with SessionLocal() as session:
            quota = get_quota(session, uid)
        assert quota == {"used": 0, "limit": 3, "remaining": 3}

        # 消费 1 次 → used=1
        with SessionLocal() as session:
            quota = consume_quota(session, uid, 1)
        assert quota == {"used": 1, "limit": 3, "remaining": 2}

        # 回补 1 次 → used=0（下限 0）
        with SessionLocal() as session:
            quota = refund_quota(session, uid, 1)
        assert quota == {"used": 0, "limit": 3, "remaining": 3}

        # 回补到 0 以下不产生负数
        with SessionLocal() as session:
            quota = refund_quota(session, uid, 2)
        assert quota["used"] == 0

        # 消费至满额后再消费 → ValueError
        with SessionLocal() as session:
            for _ in range(3):
                consume_quota(session, uid, 1)
        with SessionLocal() as session:
            with pytest.raises(ValueError):
                consume_quota(session, uid, 1)

        # 跨日重置：preferences 中 date 置为昨日 → get_quota used 归零
        yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        with SessionLocal() as session:
            user = session.get(User, uid)
            user.preferences = {"vision_quota": {"date": yesterday, "used": 3}}
            session.commit()
        with SessionLocal() as session:
            quota = get_quota(session, uid)
        assert quota["used"] == 0

        # 会员判定函数：无订单 → False
        with SessionLocal() as session:
            status = get_member_status(session, uid)
        assert status == {"is_member": False, "expire_at": None}
    finally:
        _delete_user_with_orders(anon)


# ---------------------------------------------------------------------------
# J 补齐（深度验证差距项）：订单创建幂等口径锁定 + 会员权益 vision 额度联动
# ---------------------------------------------------------------------------
def test_create_order_repeat_creates_independent_pending_orders(client: TestClient) -> None:
    """同用户重复创建订单 → 独立 pending 订单、无任何自动扣费（RL-20/21 锁定）（函数）。

    说明：
        验收口径核对结论：OrderCreateRequest 仅有 product_type（无 request_id
        幂等键），order 表亦无幂等列——「同 request_id 返回同一订单」业务未实现
        （差距与最小修复方案见交付报告，涉及 DB 迁移故本阶段不实施）。
        阶段一「不重复扣费」由以下三道锁定保障，本用例逐项断言：
        1) 重复创建仅产生独立 pending 订单（创建动作本身无扣费语义）；
        2) 全部订单 paid_at / wx_transaction_id 为空（无自动扣费）；
        3) mock-pay 仅作用于指定订单，其余订单保持 pending（状态机隔离），
           且支付前会员权益不生效（is_member=False、免费额度 3）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败；清理失败向上抛出（避免脏数据残留）。
    """
    anon = _unique_anon()
    try:
        first = _create_order(client, anon, "monthly")
        second = _create_order(client, anon, "monthly")
        # 幂等键缺失的当下语义：重复创建 = 两笔独立 pending 订单（互不影响）
        assert first["order_no"] != second["order_no"]
        for order in (first, second):
            assert order["status"] == "pending"
            assert order["paid_at"] is None
            assert order["wx_transaction_id"] is None
            assert order["amount_cents"] == 2500

        # 创建不产生任何权益：未支付维持免费档 3（无「下单即扣费」红线）
        me = client.get("/v1/member/me", headers={"X-Anonymous-Id": anon}).json()
        assert me["is_member"] is False
        assert me["quota"]["limit"] == 3
        assert me["quota"]["used"] == 0

        # mock-pay 仅作用于指定订单：另一笔保持 pending（状态机隔离，不连带扣费）
        assert client.post(f"/v1/member/orders/{first['order_no']}/mock-pay").status_code == 200
        with SessionLocal() as session:
            user = session.execute(
                select(User).where(User.anonymous_id == anon)
            ).scalar_one()
            rows = session.execute(
                select(Order).where(Order.user_id == int(user.id)).order_by(Order.id)
            ).scalars().all()
        assert len(rows) == 2
        by_no = {order.order_no: order for order in rows}
        assert by_no[first["order_no"]].status == "paid"
        assert by_no[second["order_no"]].status == "pending"
        assert by_no[second["order_no"]].paid_at is None
        assert by_no[second["order_no"]].wx_transaction_id is None
    finally:
        _delete_user_with_orders(anon)


def test_member_paid_vision_quota_linkage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """mock-pay 后会员识别额度即时生效 10/日；未支付维持免费 3（函数）。

    说明：
        vision 模块会员判定与会员口径同源（order 表存在 paid 订单，每请求直查）；
        以桩 provider（恒 high 置信）打通识别扣减链路，断言：
        - 支付前 recognize 响应 quota.limit == 3（免费档）；
        - mock-pay 成功后 recognize 响应 quota.limit == 10（会员权益即时生效）；
        - /v1/member/me 与 vision 响应的会员额度口径一致（limit 均为 10）。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 vision 模块 provider 工厂（离线桩）与留档根目录。
        tmp_path：pytest 临时目录（识别留档落 tmp，不污染 uploads）。

    返回值：
        None。

    异常：
        断言失败即测试失败；清理失败向上抛出。
    """
    from app.ability.providers import RecognizedItem, VisionProvider
    from app.api.v1 import vision as vision_module

    # 路由接线兜底（幂等）：member 测试文件独立运行时保证 vision 端点可达
    paths = {getattr(route, "path", "") for route in main_app.routes}
    if "/v1/vision/recognize" not in paths:
        main_app.include_router(vision_module.router, prefix="/v1")

    class _StubHighProvider(VisionProvider):
        """桩视觉 provider（测试用）：恒定返回 1 个 high 置信识别项（模型类）。"""

        def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
            """返回固定识别项（函数）。

            参数：
                image_bytes：图片字节（忽略）。

            返回值：
                list[RecognizedItem]：单项 high（番茄）。

            异常：
                无。
            """
            return [RecognizedItem(name="番茄", confidence="high", ingredient_id=1)]

    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubHighProvider())
    monkeypatch.setattr(vision_module, "_UPLOAD_BASE_DIR", tmp_path)

    anon = _unique_anon()
    headers = {"X-Anonymous-Id": anon}
    upload = {"file": ("photo.jpg", b"fake-jpeg-bytes-for-quota-linkage", "image/jpeg")}
    try:
        # 支付前：免费档额度 3
        before = client.post("/v1/vision/recognize", files=upload, headers=headers)
        assert before.status_code == 200
        assert before.json()["quota"]["limit"] == 3

        order = _create_order(client, anon, "monthly")
        assert client.post(f"/v1/member/orders/{order['order_no']}/mock-pay").status_code == 200

        # 支付后：会员档额度 10（权益即时生效）
        after = client.post("/v1/vision/recognize", files=upload, headers=headers)
        assert after.status_code == 200
        assert after.json()["quota"]["limit"] == 10

        # 双口径一致：/v1/member/me 与 vision 响应的会员额度相同
        me = client.get("/v1/member/me", headers=headers).json()
        assert me["is_member"] is True
        assert me["quota"]["limit"] == 10
    finally:
        _delete_user_with_orders(anon)
