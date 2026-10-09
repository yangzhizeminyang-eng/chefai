"""杂项接口集成测试。

覆盖（spec Task 6.5）：
    - GET /v1/ingredients?q=西红柿 命中番茄条目（别名搜索）；
    - GET /v1/recipes/{已发布id} 200 字段齐备；
    - GET /v1/recipes/{id}/nutrition 200（估算标注）；
    - GET /v1/config/switches 四开关 true；
    - GET /api/health 200；
    - GET /docs 200。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal


def test_ingredients_alias_search(client: TestClient) -> None:
    """别名搜索：q=西红柿 命中番茄（函数）。

    说明：
        西红柿为番茄的别名（ingredient_alias 表）；响应条目需含
        allergens/aliases 前端契约字段。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/ingredients", params={"q": "西红柿"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    names = [item["name"] for item in body["items"]]
    assert "番茄" in names
    tomato = next(item for item in body["items"] if item["name"] == "番茄")
    assert "西红柿" in (tomato["aliases"] or [])
    assert "allergens" in tomato and "allergen_codes" in tomato


def test_recipe_detail_fields(client: TestClient) -> None:
    """菜谱详情 200 字段齐备（函数）。

    说明：
        取任一已发布菜谱断言：主料/辅料/调味三段清单 + 步骤 + 致敏原 + 设备 +
        替代 + 小贴士 + 来源 + servings 缩放后用量。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        recipe_id = session.execute(
            text("SELECT id FROM recipe WHERE status='published' ORDER BY id LIMIT 1")
        ).scalar()
    assert recipe_id is not None

    resp = client.get(f"/v1/recipes/{recipe_id}", params={"servings": 4})
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "id", "title", "difficulty", "time_minutes", "servings", "calories_kcal",
        "allergen_codes", "equipment", "main_ingredients", "side_ingredients",
        "seasoning_ingredients", "steps", "substitutes", "tips", "source_label",
    ):
        assert key in body, f"菜谱详情缺少字段 {key}"
    assert body["servings"] == 4
    assert body["steps"], "步骤不应为空"
    assert body["main_ingredients"] or body["side_ingredients"], "食材清单不应为空"
    first_ing = (body["main_ingredients"] or body["side_ingredients"])[0]
    assert first_ing["amount"], "用量描述不应为空"
    assert "is_main" in first_ing and "allergens" in first_ing
    # 缩放后食材行应保留原始量化字段（任务口径附加字段）
    assert "amount_value" in first_ing and "amount_type" in first_ing


def test_recipe_nutrition_endpoint(client: TestClient) -> None:
    """营养估算端点 200（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        recipe_id = session.execute(
            text("SELECT id FROM recipe WHERE status='published' ORDER BY id LIMIT 1")
        ).scalar()
    resp = client.get(f"/v1/recipes/{recipe_id}/nutrition", params={"servings": 2})
    assert resp.status_code == 200
    body = resp.json()
    for key in ("kcal", "protein", "fat", "carbs", "sodium", "per_serving", "excluded_items", "estimate_note"):
        assert key in body
    assert body["per_serving"] == 2
    assert body["estimate_note"].startswith("估算值")


def test_recipe_not_found_404(client: TestClient) -> None:
    """不存在菜谱 → 404（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/recipes/999999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_config_switches_all_true(client: TestClient) -> None:
    """远程开关五模块全开（函数）。

    说明：
        05-V1.1 §4.4：recommend/vision/qa/payment/innovation 五开关；
        模块 O 属阶段二，阶段一仅下发 switch.innovation 配置。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/config/switches")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "recommend": True, "vision": True, "qa": True, "payment": True, "innovation": True,
    }


def test_health_endpoint(client: TestClient) -> None:
    """健康检查 200（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_docs_openapi_available(client: TestClient) -> None:
    """/docs 与 openapi.json 可访问（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    # 核心路径全部注册（含 02-V1.1 §9.1 #15 的 /v1/search 别名口径）
    for expected in (
        "/v1/auth/anonymous", "/v1/consent/disclaimer", "/v1/ingredients", "/v1/ask",
        "/v1/search", "/v1/recommend", "/v1/recipes/{recipe_id}", "/v1/recipes/{recipe_id}/nutrition",
        "/v1/cooking/sessions", "/v1/cooking/sessions/{session_id}",
        "/v1/cooking/sessions/{session_id}/finish", "/v1/trace/{request_id}", "/v1/trace",
        "/v1/config/switches",
    ):
        assert expected in paths, f"OpenAPI 缺少路径 {expected}"
