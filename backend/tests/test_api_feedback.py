"""用户反馈接口集成测试（模块 N）。

覆盖（spec Task 4 模块 N）：
    - POST /v1/feedback 正常创建 → 201（feedback_id/receipt_no=FB*/时效 24h），
      type 映射落库（bug→malfunction）、request_id 落 session_request_id；
    - GET /v1/feedback/{id} 本人回执查询 → 200 pending；他人查询 → 404；
    - 风控拦截：高危内容 → 200 blocked（rule_id 有值）且不落库；
    - content 超长 → 422；非法 type → 422。

清理约定：
    自建唯一后缀匿名用户及其反馈行，禁删种子（风控规则为种子只读消费）。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.api.v1 import feedback as feedback_api
from app.core.db import SessionLocal
from app.main import app as main_app
from app.models import Feedback, User
from tests.conftest import ensure_router_registered


def _ensure_routes_registered() -> None:
    """并行开发兜底：router.py 由其他任务负责注册（函数）。

    说明：
        router.py 属禁改文件；若其他任务尚未注册本模块路由，则在主应用上
        幂等挂载（已注册则跳过），保证本测试模块可独立运行。
        守卫统一复用 conftest.ensure_router_registered（防重复注册）。

    参数：
        无。

    返回值：
        None。

    异常：
        无。
    """
    ensure_router_registered(
        main_app,
        (feedback_api.router,),
        flag="_feedback_routes_registered",
        prefix="/v1",
        probe_paths=("/v1/feedback",),
    )


_ensure_routes_registered()


def _unique_anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：anon_test_ 前缀唯一串。

    异常：
        无。
    """
    return f"anon_test_{uuid.uuid4().hex[:12]}"


def _delete_user_with_feedback(anon_id: str) -> None:
    """清理测试用户及其反馈行（函数）。

    说明：
        feedback.user_id 外键无级联，先删反馈再删用户；仅删自建数据，禁删种子。

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
        session.execute(delete(Feedback).where(Feedback.user_id == uid))
        session.execute(delete(User).where(User.id == uid))
        session.commit()


def test_create_feedback_and_receipt(client: TestClient) -> None:
    """正常创建 → 201 回执 + 回执查询 → 200 pending（函数）。

    说明：
        type=bug 落库映射为表枚举 malfunction；request_id 落
        session_request_id 列（不改模型的映射口径，见 api/v1/feedback.py 模块头）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    rid = f"t_{uuid.uuid4().hex[:16]}"
    try:
        resp = client.post(
            "/v1/feedback",
            json={
                "content": "菜谱第 3 步的火候说明看不懂，建议补充示意图",
                "type": "bug",
                "request_id": rid,
                "image_paths": [],
            },
            headers={"X-Anonymous-Id": anon},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        feedback_id = body["feedback_id"]
        assert isinstance(feedback_id, int)
        assert body["receipt_no"].startswith("FB")
        assert body["receipt_no"] == f"FB{feedback_id}"
        assert body["expected_reply_within_hours"] == 24

        # 本人回执查询：status 来自表字段（默认 pending）
        detail = client.get(
            f"/v1/feedback/{feedback_id}", headers={"X-Anonymous-Id": anon}
        )
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["status"] == "pending"
        assert detail_body["receipt_no"] == body["receipt_no"]
        assert detail_body["created_at"]

        # 落库映射取证：bug→malfunction、request_id→session_request_id
        with SessionLocal() as session:
            row = session.get(Feedback, feedback_id)
            assert row is not None
            assert row.type == "malfunction"
            assert row.session_request_id == rid
            assert row.images == []
    finally:
        _delete_user_with_feedback(anon)


def test_feedback_blocked_by_risk_engine(client: TestClient) -> None:
    """风控拦截：高危内容 → 200 blocked 且不落库（函数）。

    说明：
        「发芽土豆削掉芽能吃吗」命中种子 FS-003 规则（input 闸门口径与
        intake_guard 一致）；拦截响应不落 feedback 行。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        resp = client.post(
            "/v1/feedback",
            json={"content": "发芽土豆削掉芽能吃吗", "type": "other"},
            headers={"X-Anonymous-Id": anon},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["blocked"] is True
        assert body["rule_id"]  # 命中规则编码（FS-003 口径）
        assert body["message"]

        # 不落库：全库无该内容的反馈行（内容为本测试独有，且拦截路径连用户行都不提交）
        with SessionLocal() as session:
            count = session.execute(
                select(func.count()).where(Feedback.content == "发芽土豆削掉芽能吃吗")
            ).scalar_one()
        assert int(count) == 0
    finally:
        _delete_user_with_feedback(anon)


def test_feedback_content_too_long_422(client: TestClient) -> None:
    """content 超长（1001 字）→ 422（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/feedback",
        json={"content": "好" * 1001, "type": "other"},
        headers={"X-Anonymous-Id": _unique_anon()},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_feedback_invalid_type_422(client: TestClient) -> None:
    """非法 type → 422（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/feedback",
        json={"content": "正常内容", "type": "complaint"},
        headers={"X-Anonymous-Id": _unique_anon()},
    )
    assert resp.status_code == 422


def test_feedback_receipt_of_other_user_404(client: TestClient) -> None:
    """他人反馈回执查询 → 404（函数）。

    说明：
        仅限本人查询：user_id 不匹配或匿名头不同一律 404，不泄露他人工单。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        created = client.post(
            "/v1/feedback",
            json={"content": "希望支持一键生成购物清单", "type": "suggestion"},
            headers={"X-Anonymous-Id": anon},
        )
        assert created.status_code == 201
        feedback_id = created.json()["feedback_id"]

        # 另一用户查询 → 404
        other = client.get(
            f"/v1/feedback/{feedback_id}",
            headers={"X-Anonymous-Id": _unique_anon()},
        )
        assert other.status_code == 404
        assert other.json()["code"] == "NOT_FOUND"
    finally:
        _delete_user_with_feedback(anon)
