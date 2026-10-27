"""首页聚合接口集成测试（模块 B）。

覆盖（spec Task 4 模块 B）：
    - GET /v1/home 新匿名用户 → 200 空降级（unfinished_session=null、expiring=[]、
      profile_hint 无档案、last_expiry_check 时间戳、seasonal_categories 非空、disclaimer 非空）；
    - 有家庭档案时 profile_hint 正确（has_profile=true、member_count 正确）；
    - entries.innovation 与 remote_config 的 switch.innovation 开关联动
      （测试内改行，try/finally 还原，不污染种子）；
    - 断点续做会话与临期库存提醒的聚合取数正确。

清理约定：
    自建唯一后缀匿名用户及其级联数据（会话/库存/档案），禁删种子。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.api.v1 import home as home_api
from app.core.db import SessionLocal
from app.main import app as main_app
from app.models import (
    CookingSession,
    Family,
    FamilyMember,
    InventoryItem,
    RemoteConfig,
    User,
)
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
        (home_api.router,),
        flag="_home_routes_registered",
        prefix="/v1",
        probe_paths=("/v1/home",),
    )


_ensure_routes_registered()


def _unique_anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：anon_test_ 前缀唯一串（自建自清理，不碰种子）。

    异常：
        无。
    """
    return f"anon_test_{uuid.uuid4().hex[:12]}"


def _delete_user_cascade(anon_id: str) -> None:
    """清理测试用户及其级联数据（函数）。

    说明：
        仅删除本测试自建匿名用户（inventory/session/family/member），禁删种子。

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
        session.execute(delete(InventoryItem).where(InventoryItem.user_id == uid))
        session.execute(delete(CookingSession).where(CookingSession.user_id == uid))
        session.execute(
            delete(FamilyMember).where(
                FamilyMember.family_id.in_(select(Family.id).where(Family.user_id == uid))
            )
        )
        session.execute(delete(Family).where(Family.user_id == uid))
        session.execute(delete(User).where(User.id == uid))
        session.commit()


def _create_user(anon_id: str) -> int:
    """直建测试用户行（函数）。

    参数：
        anon_id：匿名 ID。

    返回值：
        int：用户 ID。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as session:
        user = User(anonymous_id=anon_id)
        session.add(user)
        session.commit()
        return int(user.id)


def test_home_empty_fallback_for_new_anonymous(client: TestClient) -> None:
    """新匿名用户 → 200 空降级（函数）。

    说明：
        无会话/无库存/无档案 → unfinished_session=null、expiring=[]、
        profile_hint 无档案；时间戳/当季类别/免责声明恒有值。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        resp = client.get("/v1/home", headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 200
        body = resp.json()
        # 六入口开关齐备且默认开启
        assert body["entries"] == {
            "cooking": True, "vision": True, "seasonal": True,
            "goal": True, "fridge": True, "innovation": True,
        }
        # 空降级子项
        assert body["unfinished_session"] is None
        assert body["expiring"] == []
        assert body["profile_hint"] == {"has_profile": False, "member_count": 0}
        # 恒有值子项
        assert body["last_expiry_check"]
        assert len(body["seasonal_categories"]) >= 1
        assert body["disclaimer"]
    finally:
        _delete_user_cascade(anon)


def test_home_profile_hint(client: TestClient) -> None:
    """有家庭档案时 profile_hint 正确（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        uid = _create_user(anon)
        with SessionLocal() as session:
            family = Family(user_id=uid, name=f"测试家庭{anon[-4:]}")
            session.add(family)
            session.flush()
            session.add_all(
                [
                    FamilyMember(
                        family_id=family.id, nickname="爸爸", age_group="18-59",
                        no_known_allergen=True,
                    ),
                    FamilyMember(
                        family_id=family.id, nickname="宝宝", age_group="0-3",
                        no_known_allergen=True,
                    ),
                ]
            )
            session.commit()

        resp = client.get("/v1/home", headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 200
        assert resp.json()["profile_hint"] == {"has_profile": True, "member_count": 2}
    finally:
        _delete_user_cascade(anon)


def test_home_profile_hint_ignores_empty_family(client: TestClient) -> None:
    """自动创建但没有成员的家庭不应被展示为已建档。"""
    anon = _unique_anon()
    try:
        client.get("/v1/profile/family", headers={"X-Anonymous-Id": anon})
        resp = client.get("/v1/home", headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 200
        assert resp.json()["profile_hint"] == {"has_profile": False, "member_count": 0}
    finally:
        _delete_user_cascade(anon)


def test_home_innovation_switch_linkage(client: TestClient) -> None:
    """entries.innovation 与 switch.innovation 开关联动（函数）。

    说明：
        直接改 remote_config 行再 try/finally 还原（不污染种子）；
        config.get_switches 每请求直查，改动即时生效。

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
            select(RemoteConfig).where(RemoteConfig.config_key == "switch.innovation")
        ).scalar_one()
        original_value = row.value
        row.value = False
        session.commit()
    try:
        resp = client.get("/v1/home", headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 200
        assert resp.json()["entries"]["innovation"] is False
    finally:
        with SessionLocal() as session:
            row = session.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == "switch.innovation")
            ).scalar_one()
            row.value = original_value
            session.commit()
        _delete_user_cascade(anon)


def test_home_unfinished_session_and_expiring(client: TestClient) -> None:
    """断点续做会话 + 临期库存提醒聚合正确（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        uid = _create_user(anon)
        with SessionLocal() as session:
            recipe_id = session.execute(
                text("SELECT id FROM recipe WHERE status='published' ORDER BY id LIMIT 1")
            ).scalar()
            assert recipe_id is not None, "种子菜谱缺失（环境前置条件）"
            ingredient_ids = session.execute(
                text("SELECT id FROM ingredient ORDER BY id LIMIT 2")
            ).scalars().all()
            assert len(ingredient_ids) >= 1, "种子食材缺失（环境前置条件）"

            session.add(
                CookingSession(
                    user_id=uid, recipe_id=int(recipe_id), servings=2,
                    current_step_no=2, status="ongoing",
                    allergen_conflict=False, allergen_conflict_ack=True,
                    started_at=datetime.now(UTC),
                )
            )
            today = datetime.now(UTC).date()
            for offset, ingredient_id in enumerate(ingredient_ids[:2], start=1):
                session.add(
                    InventoryItem(
                        user_id=uid, ingredient_id=int(ingredient_id),
                        quantity_level="has", storage="fridge",
                        expiry_date=today + timedelta(days=offset),
                        status="normal", source="manual",
                    )
                )
            session.commit()

            recipe_title = session.execute(
                text("SELECT title FROM recipe WHERE id=:rid"), {"rid": int(recipe_id)}
            ).scalar()

        resp = client.get("/v1/home", headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 200
        body = resp.json()

        unfinished = body["unfinished_session"]
        assert unfinished is not None
        assert unfinished["recipe_id"] == int(recipe_id)
        assert unfinished["recipe_name"] == recipe_title
        assert unfinished["current_step"] == 2
        assert unfinished["total_steps"] >= 1

        expiring = body["expiring"]
        assert len(expiring) == 2
        assert expiring[0]["days_left"] == 1 and expiring[1]["days_left"] == 2
        for item in expiring:
            assert item["ingredient_name"]
            assert item["expire_date"]
            assert isinstance(item["allergen_codes"], list)
    finally:
        _delete_user_cascade(anon)


def test_home_no_header_returns_empty_state(client: TestClient) -> None:
    """无 X-Anonymous-Id 头 → 200 匿名空态且不创建用户行（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    before = _count_users()
    resp = client.get("/v1/home")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unfinished_session"] is None
    assert body["expiring"] == []
    assert _count_users() == before


def _count_users() -> int:
    """统计 user 表行数（函数）。

    返回值：
        int：行数。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as session:
        return int(session.execute(text('SELECT COUNT(*) FROM "user"')).scalar_one())
