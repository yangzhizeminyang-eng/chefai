"""收藏与个人中心集成测试（模块 I）。

覆盖：
    - 收藏：新建 201、重复幂等 200、分组过滤、软删 204（再删 404）、软删后可重收藏、
      菜谱不存在 404；
    - 历史：completed 会话倒序 + 评分；
    - 拿手菜：cooked 有评分聚合（次数≥2 且均分≥4 才入选）；
    - 设置：默认值合并读、合并写（未传字段保留）、字号枚举校验；
    - 导出：JSON 附件下载与结构；
    - 注销：级联清理（库存/收藏/会话/饮食记录等）且 user 行删除；
    - 烹饪求助：正常回答（1~3 条）、风控拦截（blocked）、限次 429（每次调用均计数）、
      他人会话 404。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.v1 import inventory as inventory_api
from app.api.v1 import personal as personal_api
from app.api.v1.router import api_router
from app.core.db import SessionLocal
from app.models import CookingHelpLog, User

# 并行开发约定：router.py 由集成步骤统一注册；未注册时此处补注册（进程级标记守卫，
# 避免懒加载路由下重复 include 产生 OpenAPI Duplicate Operation ID 告警）。
# 本文件覆盖导出/注销流程，需同时补注册库存与购物清单路由。
if not getattr(api_router, "_t3_inventory_registered", False):
    api_router.include_router(inventory_api.router)
    api_router.include_router(inventory_api.shopping_router)
    api_router._t3_inventory_registered = True
if not getattr(api_router, "_t3_personal_registered", False):
    api_router.include_router(personal_api.router)
    api_router._t3_personal_registered = True


def _headers(anon: str) -> dict:
    """构造带匿名身份的请求头（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        dict：X-Anonymous-Id 请求头。

    异常：
        无。
    """
    return {"X-Anonymous-Id": anon}


@pytest.fixture()
def anon_id() -> str:
    """唯一匿名 ID fixture（函数）。

    说明：
        自建数据自清理：注销测试自身已删用户，此处兜底再删一次（幂等）。

    返回值：
        str：唯一匿名 ID。

    异常：
        清理失败向上抛出。
    """
    value = f"anon_t3per_{uuid.uuid4().hex[:10]}"
    yield value
    _delete_user(value)


def _delete_user(anon: str) -> None:
    """按匿名 ID 删除用户行（级联清理自建数据）（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        None。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
        if user is not None:
            db.delete(user)
            db.commit()


def _finish_session(client: TestClient, anon: str, recipe_id: int, rating: int | None = None) -> int:
    """创建并完成一个烹饪会话（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。
        recipe_id：菜谱 ID。
        rating：评分（可 None）。

    返回值：
        int：会话 ID。

    异常：
        断言失败即测试失败。
    """
    created = client.post("/v1/cooking/sessions", json={"recipe_id": recipe_id, "servings": 2}, headers=_headers(anon))
    assert created.status_code == 200
    sid = int(created.json()["id"])
    payload = {"rating": rating} if rating is not None else {}
    finished = client.post(f"/v1/cooking/sessions/{sid}/finish", json=payload, headers=_headers(anon))
    assert finished.status_code == 200
    return sid


def test_favorite_idempotent_groups_and_soft_delete(client: TestClient, anon_id: str) -> None:
    """收藏：幂等/分组/软删/重收藏/404（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    first = client.post("/v1/favorites", json={"recipe_id": 1}, headers=_headers(anon_id))
    assert first.status_code == 201
    assert first.json()["group_name"] == "默认分组"
    assert first.json()["recipe_name"] == "番茄炒蛋"

    again = client.post("/v1/favorites", json={"recipe_id": 1}, headers=_headers(anon_id))
    assert again.status_code == 200  # 幂等返回既有
    assert again.json()["recipe_id"] == 1

    grouped = client.post("/v1/favorites", json={"recipe_id": 2, "group_name": "家常菜"}, headers=_headers(anon_id))
    assert grouped.status_code == 201

    listing = client.get("/v1/favorites", headers=_headers(anon_id)).json()
    assert set(listing["groups"]) == {"默认分组", "家常菜"}
    assert {i["recipe_id"] for i in listing["items"]} == {1, 2}
    assert set(listing["items"][0]["allergen_codes"]) == {"egg", "peanut"}  # 番茄炒蛋：鸡蛋/花生油聚合致敏原

    filtered = client.get("/v1/favorites", params={"group": "家常菜"}, headers=_headers(anon_id)).json()
    assert [i["recipe_id"] for i in filtered["items"]] == [2]

    # 软删：204；再删 404；列表不再出现；同菜谱可重新收藏
    assert client.delete("/v1/favorites/1", headers=_headers(anon_id)).status_code == 204
    assert client.delete("/v1/favorites/1", headers=_headers(anon_id)).status_code == 404
    rest = client.get("/v1/favorites", headers=_headers(anon_id)).json()
    assert 1 not in [i["recipe_id"] for i in rest["items"]]
    assert client.post("/v1/favorites", json={"recipe_id": 1}, headers=_headers(anon_id)).status_code == 201

    # 菜谱不存在 → 404
    assert client.post("/v1/favorites", json={"recipe_id": 999999999}, headers=_headers(anon_id)).status_code == 404


def test_history_and_signature_dishes(client: TestClient, anon_id: str) -> None:
    """历史倒序与拿手菜聚合（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    _finish_session(client, anon_id, 1, rating=5)
    _finish_session(client, anon_id, 1, rating=4)
    _finish_session(client, anon_id, 2, rating=3)
    _finish_session(client, anon_id, 2, rating=3)
    # 无评分会话也进历史
    _finish_session(client, anon_id, 1)

    history = client.get("/v1/history", params={"limit": 50}, headers=_headers(anon_id)).json()["items"]
    assert len(history) == 5
    assert all(h["finished_at"] for h in history)
    assert history[0]["finished_at"] >= history[-1]["finished_at"]  # 完成时间倒序
    rating_by_recipe: dict[int, list[int]] = {}
    for h in history:
        if h["rating"] is not None:
            rating_by_recipe.setdefault(h["recipe_id"], []).append(h["rating"])
    assert sorted(rating_by_recipe[1]) == [4, 5]
    assert history[0]["recipe_name"] in ("番茄炒蛋", "青椒土豆丝")

    # 拿手菜：番茄炒蛋 2 次（均分 4.5）入选；青椒土豆丝 2 次但均分 3 落选
    signature = client.get("/v1/signature-dishes", headers=_headers(anon_id)).json()["items"]
    assert [s["recipe_id"] for s in signature] == [1]
    assert signature[0]["cook_count"] == 2
    assert signature[0]["avg_rating"] == 4.5
    assert signature[0]["recipe_name"] == "番茄炒蛋"


def test_settings_merge_write(client: TestClient, anon_id: str) -> None:
    """设置：默认合并读 + 合并写（未传字段保留）（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    defaults = client.get("/v1/settings", headers=_headers(anon_id)).json()
    assert defaults == {"font_size": "normal", "unit": "metric", "voice_enabled": True, "reminder_enabled": True}

    first = client.put(
        "/v1/settings",
        json={"font_size": "large", "voice_enabled": False},
        headers=_headers(anon_id),
    )
    assert first.status_code == 200
    assert first.json()["font_size"] == "large"
    assert first.json()["voice_enabled"] is False
    assert first.json()["unit"] == "metric"  # 未传字段保留默认

    second = client.put("/v1/settings", json={"voice_enabled": True}, headers=_headers(anon_id)).json()
    assert second["font_size"] == "large"  # 合并写：上次设置保留
    assert second["voice_enabled"] is True

    assert client.get("/v1/settings", headers=_headers(anon_id)).json()["font_size"] == "large"
    # 字号枚举非法 → 422
    assert client.put("/v1/settings", json={"font_size": "huge"}, headers=_headers(anon_id)).status_code == 422


def test_export_structure_and_attachment(client: TestClient, anon_id: str) -> None:
    """数据导出：JSON 附件 + 结构完整（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert client.post("/v1/inventory", json={"ingredient_id": 1, "quantity_level": "plenty"}, headers=_headers(anon_id)).status_code == 201
    assert client.post("/v1/favorites", json={"recipe_id": 1}, headers=_headers(anon_id)).status_code == 201
    _finish_session(client, anon_id, 1, rating=5)

    resp = client.get("/v1/me/export", headers=_headers(anon_id))
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    body = resp.json()
    assert set(body) >= {"meta", "profile", "inventory", "favorites", "history", "feedbacks"}
    assert set(body["profile"]) == {"family", "members", "skill", "goal"}
    assert body["inventory"][0]["ingredient_name"] == "番茄"
    assert body["favorites"][0]["recipe_name"] == "番茄炒蛋"
    assert len(body["history"]) == 1
    assert body["feedbacks"][0]["rating"] == 5


def test_delete_me_cascades(client: TestClient, anon_id: str) -> None:
    """注销：级联清理全部自建数据并删除用户行（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    inv = client.post("/v1/inventory", json={"ingredient_id": 1, "quantity_level": "low"}, headers=_headers(anon_id)).json()
    assert client.post("/v1/shopping-list", json={"items": [{"ingredient_id": 2}]}, headers=_headers(anon_id)).status_code == 201
    assert client.post("/v1/favorites", json={"recipe_id": 1}, headers=_headers(anon_id)).status_code == 201
    sid = _finish_session(client, anon_id, 1, rating=4)
    assert client.put("/v1/settings", json={"font_size": "xlarge"}, headers=_headers(anon_id)).status_code == 200

    # 先取用户主键（注销后无法再按匿名 ID 定位），用于按 user 维度断言级联清理
    with SessionLocal() as db:
        uid = int(db.execute(select(User.id).where(User.anonymous_id == anon_id)).scalar_one())

    deleted = client.delete("/v1/me", headers=_headers(anon_id))
    assert deleted.status_code == 204

    with SessionLocal() as db:
        from app.models import (
            CookingSession,
            FavoriteRecipe,
            InventoryItem,
            MealRecord,
            ShoppingListItem,
        )

        # 用户行已删
        assert db.execute(select(User).where(User.anonymous_id == anon_id)).scalar_one_or_none() is None
        # 各业务表按 user_id 级联清理
        assert db.execute(select(InventoryItem).where(InventoryItem.id == int(inv["id"]))).scalar_one_or_none() is None
        assert db.execute(select(ShoppingListItem).where(ShoppingListItem.user_id == uid)).scalars().all() == []
        assert db.execute(select(CookingSession).where(CookingSession.id == sid)).scalar_one_or_none() is None
        assert db.execute(select(MealRecord).where(MealRecord.user_id == uid)).scalars().all() == []
        assert db.execute(select(FavoriteRecipe).where(FavoriteRecipe.user_id == uid)).scalars().all() == []

    # 注销后同 anonymous_id 再来视为新用户（auth upsert 自然新建）
    relogin = client.post("/v1/auth/anonymous", json={"anonymous_id": anon_id})
    assert relogin.status_code == 200
    assert relogin.json()["anonymous_id"] == anon_id
    assert client.get("/v1/settings", headers=_headers(anon_id)).json()["font_size"] == "normal"  # 新用户全默认


def test_help_answers_block_and_limit(client: TestClient, anon_id: str) -> None:
    """烹饪求助：正常回答 + 风控拦截 + 限次 429（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    created = client.post("/v1/cooking/sessions", json={"recipe_id": 1, "servings": 2}, headers=_headers(anon_id))
    assert created.status_code == 200
    sid = int(created.json()["id"])

    # 1) 正常回答：基于当前步骤（第 1 步），1~3 条
    first = client.post(f"/v1/cooking/sessions/{sid}/help", json={"question": "这一步要翻炒多久"}, headers=_headers(anon_id))
    assert first.status_code == 200
    body = first.json()
    assert body["blocked"] is False
    assert 1 <= len(body["answers"]) <= 3
    assert body["answers"][0].startswith("当前第 1 步：")

    # 2) 风控拦截：医疗/高危句式 → blocked，不生成回答
    blocked = client.post(
        f"/v1/cooking/sessions/{sid}/help",
        json={"question": "一岁宝宝能吃蜂蜜吗"},
        headers=_headers(anon_id),
    )
    assert blocked.status_code == 200
    blocked_body = blocked.json()
    assert blocked_body["blocked"] is True
    assert blocked_body["rule_id"] == "SP-001"
    assert blocked_body["message"]
    assert blocked_body["answers"] == []

    # 3) 第三次正常求助后达到上限
    third = client.post(f"/v1/cooking/sessions/{sid}/help", json={"question": "怎么判断咸淡"}, headers=_headers(anon_id))
    assert third.status_code == 200

    # 4) 第 4 次 → 429（每次调用均写日志计数，含被拦截调用）
    fourth = client.post(f"/v1/cooking/sessions/{sid}/help", json={"question": "还要注意什么"}, headers=_headers(anon_id))
    assert fourth.status_code == 429
    assert fourth.json()["code"] == "RATE_LIMITED"
    assert "上限" in fourth.json()["message"]

    with SessionLocal() as db:
        count = int(
            db.execute(
                select(func.count(CookingHelpLog.id)).where(CookingHelpLog.session_id == sid)
            ).scalar()
            or 0
        )
    assert count == 3  # 三次成功调用（含拦截）各留痕一条，第 4 次被拒

    # 他人会话 → 404；不存在会话 → 404
    other_anon = f"anon_t3per_{uuid.uuid4().hex[:10]}"
    try:
        assert (
            client.post(
                f"/v1/cooking/sessions/{sid}/help",
                json={"question": "这个锅要开多大火"},
                headers=_headers(other_anon),
            ).status_code
            == 404
        )
    finally:
        _delete_user(other_anon)
    assert client.post("/v1/cooking/sessions/999999999/help", json={"question": "在吗"}, headers=_headers(anon_id)).status_code == 404
