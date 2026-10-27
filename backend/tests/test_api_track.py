"""用户行为埋点接口集成测试（POST/GET /v1/track/events）。

覆盖（埋点接收闭环任务清单）：
    - 批量接收 200：accepted/discarded 计数，事件落库（anonymous_id/properties）；
    - 批量超 TRACK_BATCH_MAX（50 条）→ 422 拒绝整批；
    - 事件名白名单（38 客户端事件 + 运维事件 app_error）：白名单外单条丢弃并计数；
    - 单条 props 超过 TRACK_ITEM_MAX_BYTES（4KB）→ 丢弃并计数（同批其余正常接收）；
    - X-Anonymous-Id 头透传落库；无头允许（anonymous_id 存 NULL，记纯匿名）；
    - 敏感字段剥离：properties 中 password/token/cookie/authorization/api_key
      等键（含嵌套）值删除后再存储，断言库中原值不存在；
    - 安全事件（safety_block 等 SAFETY_EVENTS）仍存但同样剥敏感；
    - GET /v1/track/events 管理员授权查询：无凭证/伪造 token 401，
      管理员登录后 200 且能查到已接收事件；
    - 保留天数清理函数 purge_expired_track_events：超期行删除、新行保留。

清理约定：
    事件行按匿名 ID / request_id 前缀自建自清理，管理员账号自建自删，禁删种子。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.v1.track import purge_expired_track_events
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import app as main_app
from app.models import AdminUser, TrackEvent

# 唯一后缀：本次运行全部自建行以此命名，保证可重复执行
SUFFIX = uuid.uuid4().hex[:8]

# 自建管理员账号（管理员查询测试用）
_ADMIN_USER = f"trkadmin_{SUFFIX}"
_ADMIN_PWD = "Trk@123456"

# 匿名 ID 前缀（清理依据）
_ANON_PREFIX = f"anon_trk_{SUFFIX}_"


def _anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：统一前缀唯一串（清理按前缀兜底）。

    异常：
        无。
    """
    return f"{_ANON_PREFIX}{uuid.uuid4().hex[:12]}"


def _cleanup(anon_ids: list[str], admin_username: str | None = None) -> None:
    """清理测试自建行（函数）。

    说明：
        按匿名 ID 删事件行；管理员账号按用户名删除。仅删自建数据，禁删种子。

    参数：
        anon_ids：待清理的匿名 ID 列表。
        admin_username：待清理的管理员用户名（可 None）。

    返回值：
        None。

    异常：
        数据库异常向上抛出（清理失败即测试失败，避免脏数据残留）。
    """
    with SessionLocal() as session:
        for anon in anon_ids:
            session.execute(delete(TrackEvent).where(TrackEvent.anonymous_id == anon))
        if admin_username:
            session.execute(delete(AdminUser).where(AdminUser.username == admin_username))
        session.commit()


def _evt(name: str, props: dict | None = None) -> dict:
    """构造一条客户端口径事件（函数）。

    说明：
        结构与 web-mini TrackEventPayload 一致：{name, props, ts, request_id}。

    参数：
        name：事件名。
        props：事件属性（可 None 表示不带 props 字段）。

    返回值：
        dict：事件负载。

    异常：
        无。
    """
    payload: dict = {
        "name": name,
        "ts": 1760000000000,
        "request_id": f"t_{uuid.uuid4().hex[:16]}",
    }
    if props is not None:
        payload["props"] = props
    return payload


def _post_events(client: TestClient, events: list[dict], anon: str | None = None):
    """POST /v1/track/events 便捷封装（函数）。

    参数：
        client：TestClient。
        events：事件数组。
        anon：匿名 ID（None 表示不带 X-Anonymous-Id 头）。

    返回值：
        httpx.Response：接口响应。

    异常：
        无。
    """
    headers = {"X-Anonymous-Id": anon} if anon else {}
    return client.post("/v1/track/events", json={"events": events}, headers=headers)


def _login_admin() -> dict:
    """创建自建管理员并登录，返回鉴权头（函数）。

    说明：
        先幂等删除同名账号再创建（super_admin/active），经 /admin/v1/auth/login
        换取 access_token。

    返回值：
        dict：{"Authorization": "Bearer <token>"}。

    异常：
        AssertionError：登录失败（测试环境前置条件）。
    """
    with SessionLocal() as session:
        session.execute(delete(AdminUser).where(AdminUser.username == _ADMIN_USER))
        session.add(
            AdminUser(
                username=_ADMIN_USER,
                password_hash=hash_password(_ADMIN_PWD),
                role="super_admin",
                status="active",
            )
        )
        session.commit()
    with TestClient(main_app) as c:
        resp = c.post(
            "/admin/v1/auth/login",
            json={"username": _ADMIN_USER, "password": _ADMIN_PWD},
        )
    assert resp.status_code == 200, f"管理员登录失败: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_batch_accept_200_and_persist(client: TestClient) -> None:
    """批量接收 200 并落库（函数）。

    说明：
        两条合法事件整批接收 accepted=2；落库行含事件名、属性与匿名 ID。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        resp = _post_events(
            client,
            [_evt("app_enter", {"scene": "home"}), _evt("cook_complete", {"recipe_id": 1})],
            anon=anon,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] == 2
        assert body["discarded"] == 0

        with SessionLocal() as session:
            rows = (
                session.execute(
                    select(TrackEvent)
                    .where(TrackEvent.anonymous_id == anon)
                    .order_by(TrackEvent.id)
                )
                .scalars()
                .all()
            )
            assert len(rows) == 2
            assert rows[0].event_name == "app_enter"
            assert rows[0].properties == {"scene": "home"}
            assert rows[1].event_name == "cook_complete"
    finally:
        _cleanup([anon])


def test_batch_over_max_422(client: TestClient) -> None:
    """批量超 TRACK_BATCH_MAX（51 条）→ 422 整批拒绝（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        resp = _post_events(client, [_evt("app_enter") for _ in range(51)], anon=anon)
        assert resp.status_code == 422, resp.text
    finally:
        _cleanup([anon])


def test_unknown_event_discarded_and_counted(client: TestClient) -> None:
    """白名单外事件单条丢弃并计数（函数）。

    说明：
        同批 1 合法 + 1 未知事件名：accepted=1、discarded=1，未知事件不落库。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        resp = _post_events(
            client, [_evt("app_enter"), _evt(f"bogus_evt_{SUFFIX}")], anon=anon
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] == 1
        assert body["discarded"] == 1

        with SessionLocal() as session:
            names = (
                session.execute(
                    select(TrackEvent.event_name).where(TrackEvent.anonymous_id == anon)
                )
                .scalars()
                .all()
            )
            assert names == ["app_enter"]
    finally:
        _cleanup([anon])


def test_oversized_props_discarded_and_counted(client: TestClient) -> None:
    """单条 props 超过 4KB → 丢弃并计数（函数）。

    说明：
        同批 1 条 5KB props + 1 条正常：accepted=1、discarded=1；超限条不落库。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        big = {"blob": "x" * 5000}
        resp = _post_events(
            client,
            [_evt("recommend_request", big), _evt("app_enter")],
            anon=anon,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] == 1
        assert body["discarded"] == 1

        with SessionLocal() as session:
            names = (
                session.execute(
                    select(TrackEvent.event_name).where(TrackEvent.anonymous_id == anon)
                )
                .scalars()
                .all()
            )
            assert names == ["app_enter"]
    finally:
        _cleanup([anon])


def test_anonymous_id_header_passthrough(client: TestClient) -> None:
    """X-Anonymous-Id 头透传落库（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        resp = _post_events(client, [_evt("app_enter")], anon=anon)
        assert resp.status_code == 200, resp.text

        with SessionLocal() as session:
            row = session.execute(
                select(TrackEvent).where(TrackEvent.anonymous_id == anon)
            ).scalar_one_or_none()
            assert row is not None
            assert row.anonymous_id == anon
    finally:
        _cleanup([anon])


def test_missing_header_allowed_and_recorded_anonymous(client: TestClient) -> None:
    """无 X-Anonymous-Id 头：允许接收且记纯匿名（anonymous_id=NULL）（函数）。

    说明：
        无头不 4xx；按 request_id 精确定位该行断言 anonymous_id 为 NULL。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    evt = _evt("app_enter")
    try:
        resp = _post_events(client, [evt])
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1

        with SessionLocal() as session:
            row = session.execute(
                select(TrackEvent).where(TrackEvent.request_id == evt["request_id"])
            ).scalar_one_or_none()
            assert row is not None
            assert row.anonymous_id is None
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(TrackEvent).where(TrackEvent.request_id == evt["request_id"])
            )
            session.commit()


def test_sensitive_keys_stripped_before_persist(client: TestClient) -> None:
    """敏感字段剥离后再存储（函数）。

    说明：
        props 含顶层 password/Authorization/api_key/cookie 与嵌套 token：原值
        不得出现在落库 JSON 任何位置；非敏感键保留。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    secret_pw = f"pw_{uuid.uuid4().hex[:8]}"
    secret_tok = f"tk_{uuid.uuid4().hex[:8]}"
    try:
        props = {
            "password": secret_pw,
            "Authorization": f"Bearer {secret_tok}",
            "api_key": "sk-test-123",
            "cookie": "sid=abc",
            "nested": {"token": secret_tok},
            "scene": "login",
        }
        resp = _post_events(client, [_evt("app_enter", props)], anon=anon)
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1

        with SessionLocal() as session:
            row = session.execute(
                select(TrackEvent).where(TrackEvent.anonymous_id == anon)
            ).scalar_one_or_none()
            assert row is not None
            dumped = json.dumps(row.properties, ensure_ascii=False)
            assert secret_pw not in dumped
            assert secret_tok not in dumped
            assert "sk-test-123" not in dumped
            assert "sid=abc" not in dumped
            assert row.properties.get("scene") == "login"
    finally:
        _cleanup([anon])


def test_safety_event_persisted_with_stripped_props(client: TestClient) -> None:
    """安全事件仍存但剥敏感（函数）。

    说明：
        safety_block 属合规举证类事件：正常接收落库，敏感键值剥离，
        业务字段（rule）保留。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    secret_tok = f"tk_{uuid.uuid4().hex[:8]}"
    try:
        resp = _post_events(
            client,
            [_evt("safety_block", {"rule": "FS-001", "token": secret_tok})],
            anon=anon,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1

        with SessionLocal() as session:
            row = session.execute(
                select(TrackEvent).where(TrackEvent.anonymous_id == anon)
            ).scalar_one_or_none()
            assert row is not None
            assert row.event_name == "safety_block"
            dumped = json.dumps(row.properties, ensure_ascii=False)
            assert secret_tok not in dumped
            assert row.properties.get("rule") == "FS-001"
    finally:
        _cleanup([anon])


def test_admin_query_requires_auth(client: TestClient) -> None:
    """GET /v1/track/events 管理员守卫（函数）。

    说明：
        无凭证 / 伪造 token → 401；管理员登录后 → 200 且能查到先前接收的事件。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        created = _post_events(client, [_evt("app_enter")], anon=anon)
        assert created.status_code == 200, created.text

        no_auth = client.get("/v1/track/events")
        assert no_auth.status_code == 401

        bad_token = client.get(
            "/v1/track/events", headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert bad_token.status_code == 401

        headers = _login_admin()
        ok = client.get("/v1/track/events", headers=headers)
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["total"] >= 1
        assert "app_enter" in [item["event_name"] for item in body["items"]]
    finally:
        _cleanup([anon], _ADMIN_USER)


def test_retention_purge_expired(client: TestClient) -> None:
    """保留天数清理函数：超期删除、新行保留（函数）。

    说明：
        插入 40 天前与当前两条事件，purge_expired_track_events(retention_days=30)
        删除超期行并返回删除条数 ≥1；未超期行保留。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _anon()
    try:
        now = datetime.now(UTC)
        with SessionLocal() as session:
            session.add_all(
                [
                    TrackEvent(
                        anonymous_id=anon,
                        event_name="app_enter",
                        properties={},
                        created_at=now - timedelta(days=40),
                    ),
                    TrackEvent(
                        anonymous_id=anon,
                        event_name="cook_complete",
                        properties={},
                        created_at=now,
                    ),
                ]
            )
            session.commit()

        with SessionLocal() as session:
            removed = purge_expired_track_events(session, retention_days=30)
            session.commit()
        assert removed >= 1

        with SessionLocal() as session:
            left = (
                session.execute(
                    select(TrackEvent).where(TrackEvent.anonymous_id == anon)
                )
                .scalars()
                .all()
            )
            assert len(left) == 1
            assert left[0].event_name == "cook_complete"
    finally:
        _cleanup([anon])
