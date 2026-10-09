"""营养口径一致性集成测试（缺陷 M5/R4/S9 回归）。

覆盖：
    - 同菜谱同输入 3 次营养请求结果一致（kcal 稳定不漂移）；
    - 唯一口径 = 每份 kcal：详情接口 calories_kcal 与营养接口 kcal 同源；
    - 单份 / 按份数合计换算闭环：total = 每份 × 份数；
    - 校验回退链：DB 值无效 / LLM 输出异常值 → 确定性回退（食材营养表求和 / 份数）；
    - LLM 有效输出落定写回 DB（后续请求直接命中库值，消除输出随机性）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ability import nutrition as nutrition_mod
from app.ability.nutrition import (
    KCAL_SOURCE_FALLBACK,
    KCAL_SOURCE_LLM,
    KCAL_SOURCE_SEED,
    estimate_recipe_nutrition,
    resolve_per_serving_kcal,
)
from app.core.db import SessionLocal
from app.models import Ingredient, Recipe, RecipeIngredient


def _pick_published_recipe_with_kcal(session: Session) -> Recipe:
    """取一道带 calories_kcal 的已发布种子菜谱（函数）。

    参数：
        session：数据库会话。

    返回值：
        Recipe：菜谱 ORM 实例。

    异常：
        断言失败即测试失败（种子环境异常）。
    """
    recipe = session.execute(
        select(Recipe)
        .where(Recipe.status == "published", Recipe.calories_kcal.is_not(None))
        .order_by(Recipe.id)
        .limit(1)
    ).scalar_one()
    assert recipe is not None, "种子缺少带 calories_kcal 的已发布菜谱"
    return recipe


def test_nutrition_consistent_across_three_requests(client: TestClient) -> None:
    """同菜谱 3 次营养请求结果一致（函数）。

    说明：
        唯一口径 = 每份 kcal 且 DB 值优先：3 次请求 kcal / kcal_source 完全一致，
        且等于菜谱库 calories_kcal（recipe_seed 来源），不再出现 262 vs 6.5 的漂移。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        recipe = _pick_published_recipe_with_kcal(session)
        recipe_id = int(recipe.id)
        db_kcal = float(recipe.calories_kcal)  # type: ignore[arg-type]

    results: list[dict[str, Any]] = []
    for _ in range(3):
        resp = client.get(f"/v1/recipes/{recipe_id}/nutrition", params={"servings": 2})
        assert resp.status_code == 200
        results.append(resp.json())

    first = results[0]
    assert first["kcal_source"] == KCAL_SOURCE_SEED, "带库值的菜谱应直接采信 DB 来源"
    assert first["kcal"] == pytest.approx(db_kcal), "每份 kcal 应等于 DB calories_kcal"
    for other in results[1:]:
        assert other["kcal"] == first["kcal"], "3 次请求每份 kcal 必须一致"
        assert other["kcal_source"] == first["kcal_source"]


def test_detail_and_nutrition_same_per_serving_kcal(client: TestClient) -> None:
    """详情头部与营养区同源同口径（函数）。

    说明：
        详情接口 calories_kcal（头部「X kcal/份」）与营养接口 kcal（每份口径）
        必须同源相等，消除「460 kcal/份 vs 117.2 kcal」矛盾。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        recipe = _pick_published_recipe_with_kcal(session)
        recipe_id = int(recipe.id)

    detail = client.get(f"/v1/recipes/{recipe_id}").json()
    nutrition = client.get(f"/v1/recipes/{recipe_id}/nutrition").json()
    assert detail["calories_kcal"] == nutrition["kcal"], "头部与营养区必须同源（每份 kcal）"
    assert nutrition["total"] is not None, "营养接口应返回按份数合计结构"


def test_per_serving_total_conversion(client: TestClient) -> None:
    """单份 / 按份数合计换算闭环（函数）。

    说明：
        total = 每份 × 份数（servings=2/4 双档验证）；每份 kcal 为 DB 每份口径，
        不随请求份数变化（区别于旧行为的总量口径误标）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        recipe = _pick_published_recipe_with_kcal(session)
        recipe_id = int(recipe.id)
        db_kcal = float(recipe.calories_kcal)  # type: ignore[arg-type]

    resp2 = client.get(f"/v1/recipes/{recipe_id}/nutrition", params={"servings": 2}).json()
    resp4 = client.get(f"/v1/recipes/{recipe_id}/nutrition", params={"servings": 4}).json()

    # 每份口径不随份数漂移（DB 值优先）
    assert resp2["kcal"] == pytest.approx(db_kcal)
    assert resp4["kcal"] == pytest.approx(db_kcal)
    # 合计 = 每份 × 份数（同源换算闭环）
    assert resp2["total"]["kcal"] == pytest.approx(db_kcal * 2, abs=0.1)
    assert resp4["total"]["kcal"] == pytest.approx(db_kcal * 4, abs=0.2)
    # 旧口径矛盾复现断言：合计不再被标成单份口径（total ≠ kcal）
    assert resp4["total"]["kcal"] != resp4["kcal"]


def _create_temp_recipe(session: Session, *, kcal: float | None, ingredient: Ingredient) -> Recipe:
    """构造临时测试菜谱（含 1 条番茄食材行，函数）。

    说明：
        flush 使本会话内查询可见；是否 commit 由调用方决定（LLM 落定路径需真实入库）。

    参数：
        session：数据库会话。
        kcal：每份热量（None 模拟库值缺失）。
        ingredient：引用的食材（须有营养数据）。

    返回值：
        Recipe：已 flush 的临时菜谱 ORM 实例。

    异常：
        无（数据库异常向上抛出由测试收尾清理）。
    """
    recipe = Recipe(
        title="__test_kcal_consistency__",
        difficulty=1,
        servings=2,
        calories_kcal=kcal,
        status="published",
        version=1,
        source_label="pytest-fixture",
        source_license="Unlicense",
        tips="",
        substitutes=[],
    )
    recipe.ingredients.append(
        RecipeIngredient(
            ingredient_id=int(ingredient.id),
            amount_value=300,
            amount_unit="g",
            amount_type="main",
            sort_order=0,
        )
    )
    session.add(recipe)
    session.flush()
    return recipe


def _pick_ingredient_with_nutrition(session: Session) -> Ingredient:
    """取一个有营养数据的食材（函数）。

    参数：
        session：数据库会话。

    返回值：
        Ingredient：食材 ORM 实例。

    异常：
        断言失败即测试失败（种子环境异常）。
    """
    ing_id = session.execute(
        text(
            "SELECT i.id FROM ingredient i "
            "JOIN ingredient_nutrition n ON n.ingredient_id = i.id "
            "WHERE n.kcal_100g IS NOT NULL ORDER BY i.id LIMIT 1"
        )
    ).scalar_one()
    ing = session.execute(select(Ingredient).where(Ingredient.id == int(ing_id))).scalar_one()
    assert ing is not None, "种子缺少带营养数据的食材"
    return ing


def test_llm_invalid_value_falls_back_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 输出异常值 → 确定性回退（函数）。

    说明：
        库值缺失 + LLM 返回 9999（>2000 无效）时，resolve_per_serving_kcal
        必须拒绝该值并回退食材营养聚合（每份 = 聚合总量 / 份数），
        且与 estimate_recipe_nutrition 的确定性结果一致。

    参数：
        monkeypatch：pytest 打桩（替换 LLM 估算函数）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(nutrition_mod, "estimate_kcal_by_llm", lambda *_a, **_k: 9999.0)
    with SessionLocal() as session:
        ingredient = _pick_ingredient_with_nutrition(session)
        recipe = _create_temp_recipe(session, kcal=None, ingredient=ingredient)
        expected = estimate_recipe_nutrition(session, int(recipe.id), servings=2)
        fallback_kcal, source = resolve_per_serving_kcal(session, recipe, 2)
        session.rollback()  # 未走 commit 路径，回滚清理临时数据

    assert source == KCAL_SOURCE_FALLBACK, "LLM 异常值应被拒绝并走确定性回退"
    assert fallback_kcal is not None
    assert fallback_kcal == pytest.approx(float(expected["per_serving"]["kcal"]), abs=0.1)


def test_llm_valid_value_persisted_then_stable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """LLM 有效输出落定写回 DB，后续请求稳定（函数）。

    说明：
        库值缺失 + LLM 返回合法值（350）→ 本次请求返回 350（llm_estimate）
        并落定入库；随后不接 LLM 桩的 API 请求直接命中库值（recipe_seed），
        同输入多次请求结果一致。

    参数：
        monkeypatch：pytest 打桩（替换 LLM 估算函数）。
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败；临时菜谱在 finally 中清理。
    """
    monkeypatch.setattr(nutrition_mod, "estimate_kcal_by_llm", lambda *_a, **_k: 350.0)
    recipe_id: int | None = None
    try:
        with SessionLocal() as session:
            ingredient = _pick_ingredient_with_nutrition(session)
            recipe = _create_temp_recipe(session, kcal=None, ingredient=ingredient)
            recipe.calories_kcal = None
            session.commit()
            recipe_id = int(recipe.id)
            kcal, source = resolve_per_serving_kcal(session, recipe, 2)
            assert source == KCAL_SOURCE_LLM, "LLM 合法输出应标记 llm_estimate 来源"
            assert kcal == pytest.approx(350.0)

        # 落定后：API 不带 LLM 桩也应命中库值（同输入一致）
        resp = client.get(f"/v1/recipes/{recipe_id}/nutrition", params={"servings": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert body["kcal"] == pytest.approx(350.0), "落定后应直接采信库值"
        assert body["kcal_source"] == KCAL_SOURCE_SEED
    finally:
        if recipe_id is not None:
            with SessionLocal() as cleanup:
                row = cleanup.execute(select(Recipe).where(Recipe.id == recipe_id)).scalar_one_or_none()
                if row is not None:
                    cleanup.delete(row)
                    cleanup.commit()


def test_invalid_db_kcal_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB 值超出合理区间 → 拒绝并走回退链（函数）。

    说明：
        模拟脏数据：库值 3（< 5 下限）不应被采信；LLM 不可用（返回 None）时
        最终落到确定性回退（食材聚合每份值）。

    参数：
        monkeypatch：pytest 打桩（替换 LLM 估算函数返回 None）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(nutrition_mod, "estimate_kcal_by_llm", lambda *_a, **_k: None)
    with SessionLocal() as session:
        ingredient = _pick_ingredient_with_nutrition(session)
        recipe = _create_temp_recipe(session, kcal=3, ingredient=ingredient)
        expected = estimate_recipe_nutrition(session, int(recipe.id), servings=2)
        fallback_kcal, source = resolve_per_serving_kcal(session, recipe, 2)
        session.rollback()

    assert source == KCAL_SOURCE_FALLBACK
    assert fallback_kcal is not None
    assert fallback_kcal == pytest.approx(float(expected["per_serving"]["kcal"]), abs=0.1)
    # 回退值自身必须落在合理区间（不会被再次判无效）
    assert 5 <= fallback_kcal <= 2000
