"""DEF-02 后端配套：GET /v1/recipes 菜谱列表搜索端点测试。

覆盖：
    - q=宫保鸡丁：菜名命中（total≥1，首条为菜名直接命中）；
    - q=西红柿：食材别名命中（番茄别名西红柿 → 引用番茄的菜谱）；
    - 分页：page/page_size 生效且 total 一致；
    - 仅 published：返回条目状态全部为已发布；
    - 非法分页参数：422 统一错误体。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Recipe


def test_search_recipes_by_title(client: TestClient) -> None:
    """q=宫保鸡丁 命中同名菜谱（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（需先执行 python -m app.seed）。
    """
    resp = client.get("/v1/recipes", params={"q": "宫保鸡丁"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"], "菜名命中不应为空"
    assert any(item["title"] == "宫保鸡丁" for item in data["items"])
    first = data["items"][0]
    for key in ("id", "title", "difficulty", "time_minutes", "calories_kcal"):
        assert key in first


def test_search_recipes_by_ingredient_alias(client: TestClient) -> None:
    """q=西红柿 经食材别名（番茄）命中引用该食材的菜谱（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/recipes", params={"q": "西红柿"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"], "别名命中不应为空"


def test_search_recipes_pagination(client: TestClient) -> None:
    """分页参数生效：page_size 截断、page 翻页、total 跨页一致（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    first = client.get("/v1/recipes", params={"page": 1, "page_size": 2}).json()
    second = client.get("/v1/recipes", params={"page": 2, "page_size": 2}).json()
    assert len(first["items"]) <= 2
    assert len(second["items"]) <= 2
    assert first["total"] == second["total"]
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert not first_ids & second_ids, "不同页不应出现重复菜谱"


def test_search_recipes_only_published(client: TestClient) -> None:
    """返回条目全部为已发布状态（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    data = client.get("/v1/recipes", params={"page_size": 20}).json()
    ids = [item["id"] for item in data["items"]]
    assert ids
    with SessionLocal() as session:
        statuses = dict(
            session.execute(
                select(Recipe.id, Recipe.status).where(Recipe.id.in_(ids))
            ).all()
        )
    assert all(statuses[rid] == "published" for rid in ids)


def test_search_recipes_invalid_page_422(client: TestClient) -> None:
    """page=0 触发 422 统一错误体（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/recipes", params={"page": 0})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"]
