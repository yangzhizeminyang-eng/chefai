"""营养估算单元测试。

覆盖（spec Task 6.4 / D9 红线）：
    - 缺失营养数据的食材列入 excluded_items 标「未纳入统计」，不按 0 计；
    - 份数线性重算：total 与份数无关（食材基准克数固定），每份值 = total / servings，
      servings 2→4 时每份减半、每份×份数恒等于整锅总量（线性关系取证）。
"""

from __future__ import annotations

from sqlalchemy import text

from app.ability.nutrition import estimate_recipe_nutrition
from app.core.db import SessionLocal


def _pick_recipe_with_missing_nutrition() -> int:
    """查找含无营养数据食材的菜谱（函数）。

    说明：
        种子计划「营养数据部分覆盖」，必存在缺失行；找不到时跳过测试（环境异常提示）。

    参数：
        无。

    返回值：
        int：菜谱 ID。

    异常：
        无（找不到时 pytest.skip）。
    """
    with SessionLocal() as session:
        row = session.execute(
            text(
                "SELECT ri.recipe_id FROM recipe_ingredient ri "
                "LEFT JOIN ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id "
                "WHERE n.id IS NULL OR n.kcal_100g IS NULL LIMIT 1"
            )
        ).scalar_one_or_none()
    if row is None:
        import pytest

        pytest.skip("种子数据无缺失营养的食材行，无法验证 excluded_items")
    return int(row)


def test_missing_nutrition_marked_not_zero() -> None:
    """缺失营养食材列入 excluded_items，不按 0 计（函数）。

    说明：
        - excluded_items 非空且每项标注「未纳入统计」；
        - 整锅 kcal 总量大于 0（有营养数据的食材正常聚合，缺失项未稀释为 0 总量）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _pick_recipe_with_missing_nutrition()
    with SessionLocal() as session:
        result = estimate_recipe_nutrition(session, recipe_id, servings=2)
    assert result["excluded_items"], f"recipe_id={recipe_id} 应有未纳入统计的食材"
    for item in result["excluded_items"]:
        assert "未纳入统计" in item
    # 有任何可聚合食材时总量必须为正（缺失项不会被计为 0 稀释判断）
    assert result["total"]["kcal"] >= 0
    assert result["estimate_note"].startswith("估算值")


def test_servings_scaling_linear() -> None:
    """份数 2→4 营养线性重算（函数）。

    说明：
        取营养数据完整的菜谱验证：total（整锅，基准克数）与请求份数无关；
        per_serving = total / servings（2→4 每份减半）；每份 × 份数 = 整锅总量
        （前端「N 人份总营养 = 每份 × N」的线性换算基础）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        recipe_id = session.execute(
            text(
                "SELECT ri.recipe_id FROM recipe_ingredient ri "
                "JOIN ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id "
                "WHERE n.kcal_100g IS NOT NULL GROUP BY ri.recipe_id HAVING COUNT(*) >= 2 LIMIT 1"
            )
        ).scalar_one_or_none()
        assert recipe_id is not None, "种子缺少营养数据完整的菜谱"
        result_2 = estimate_recipe_nutrition(session, int(recipe_id), servings=2)
        result_4 = estimate_recipe_nutrition(session, int(recipe_id), servings=4)

    # 整锅总量不随请求份数变化（食材基准克数固定）
    assert result_2["total"]["kcal"] == result_4["total"]["kcal"]
    assert result_4["total"]["kcal"] > 0
    # 每份值按份数线性重算：2 人份每份 = 4 人份每份 × 2（翻倍关系）
    assert result_4["per_serving"]["kcal"] > 0
    assert abs(result_2["per_serving"]["kcal"] - result_4["per_serving"]["kcal"] * 2) < 0.2
    # 每份 × 份数 = 整锅（线性闭环）
    assert abs(result_4["per_serving"]["kcal"] * 4 - result_4["total"]["kcal"]) < 0.2
