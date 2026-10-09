"""营养估算模块。

职责：
    按菜谱逐食材估算营养：食材营养（每 100g）× 克数 / 100 后聚合。
    - 克数规则：amount_value 且单位可换算（g/ml→1，勺→15，个→按 UNIT_GRAMS 兜底表，
      未收录取默认 50g）；amount_value 缺失时取 (amount_min + amount_max) / 2；
    - 无营养数据的食材列入 excluded_items 标「XX 未纳入统计」，🔴 不得按 0 计（spec D9）；
    - 返回总量与每份营养（随份数线性重算），固定标注「估算值，非实测值，误差约 ±15%」。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import IngredientNutrition, Recipe, RecipeIngredient

logger = get_logger(__name__)

# 「个/只/根」等计数单位的克重兜底表（常见食材经验值；未收录取 _DEFAULT_PIECE_GRAMS）
UNIT_GRAMS: dict[str, float] = {
    "鸡蛋": 50,
    "鸭蛋": 60,
    "土豆": 150,
    "番茄": 150,
    "西红柿": 150,
    "青椒": 80,
    "黄瓜": 150,
    "胡萝卜": 100,
    "洋葱": 150,
    "白萝卜": 300,
    "冬瓜": 500,
    "茄子": 150,
    "豆腐": 300,
    "馒头": 100,
    "苹果": 200,
    "香蕉": 120,
    "香菇": 30,
    "大蒜": 6,
}

# 计数单位未收录食材时的默认克重
_DEFAULT_PIECE_GRAMS = 50.0

# 单位 → 克数换算系数（ml 密度按 1 近似）
_UNIT_FACTOR: dict[str, float] = {
    "g": 1.0,
    "克": 1.0,
    "ml": 1.0,
    "毫升": 1.0,
    "勺": 15.0,   # 1 勺 ≈ 15ml（seed 数据参照口径）
    "大勺": 15.0,
    "小勺": 5.0,
    "瓣": 3.0,    # 蒜瓣近似
}

# 营养估算固定标注
ESTIMATE_NOTE = "估算值，非实测值，误差约 ±15%"

# 营养字段集合
_NUTRIENT_FIELDS = ("kcal", "protein_g", "fat_g", "carbs_g", "sodium_mg")


def _resolve_grams(amount_value, amount_min, amount_max, unit: str | None, ingredient_name: str) -> float | None:
    """解析单条食材引用的克重（函数）。

    说明：
        优先 amount_value × 单位系数；单位为「个」类计数单位时按 UNIT_GRAMS 兜底表取值；
        amount_value 缺失时取 (amount_min + amount_max) / 2（区间中值）。

    参数：
        amount_value：固定用量值（可 None）。
        amount_min：区间下限（可 None）。
        amount_max：区间上限（可 None）。
        unit：用量单位（g/ml/勺/个 等）。
        ingredient_name：食材名（用于计数单位克重表查询）。

    返回值：
        float | None：换算后的克数；无法换算（未知单位等）返回 None（该项计入 excluded_items）。

    异常：
        不抛出（数值异常返回 None）。
    """
    try:
        value = float(amount_value) if amount_value is not None else None
        if value is None and amount_min is not None and amount_max is not None:
            # 区间用量取中值
            value = (float(amount_min) + float(amount_max)) / 2.0
        if value is None:
            return None
        unit_key = (unit or "g").strip().lower()
        factor = _UNIT_FACTOR.get(unit_key)
        if factor is not None:
            return value * factor
        # 「个/只/根」等计数单位：查兜底克重表，未收录取默认
        return value * UNIT_GRAMS.get(ingredient_name, _DEFAULT_PIECE_GRAMS)
    except Exception:  # noqa: BLE001
        return None


def estimate_recipe_nutrition(session: Session, recipe_id: int, servings: int = 2) -> dict:
    """估算菜谱营养（函数）。

    说明：
        逐食材聚合：营养(每100g) × 克数 / 100；无营养数据的食材计入 excluded_items
        （「XX 未纳入统计」，不按 0 计）；总量与每份值随份数线性换算。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID。
        servings：份数，默认 2（须 ≥1，非法值按 1 处理）。

    返回值：
        dict：{
            recipe_id, servings,
            total: {kcal, protein_g, fat_g, carbs_g, sodium_mg},      # 整菜总量
            per_serving: 同结构 / servings,                            # 每份值
            excluded_items: ["XX 未纳入统计", ...],
            estimate_note: "估算值，非实测值，误差约 ±15%",
        }。

    异常：
        不抛出（菜谱不存在/查询异常时返回带 unavailable 标记的空结构，由上层标注降级）。
    """
    if not servings or int(servings) < 1:
        servings = 1
    empty = {
        "recipe_id": recipe_id,
        "servings": int(servings),
        "total": {f: 0.0 for f in _NUTRIENT_FIELDS},
        "per_serving": {f: 0.0 for f in _NUTRIENT_FIELDS},
        "excluded_items": [],
        "estimate_note": ESTIMATE_NOTE,
    }
    try:
        recipe = session.execute(select(Recipe).where(Recipe.id == recipe_id)).scalar_one_or_none()
        if recipe is None:
            empty = dict(empty)
            empty["excluded_items"] = ["菜谱不存在或营养数据暂不可用"]
            return empty
        return _aggregate(session, recipe_id, int(servings))
    except Exception as exc:  # noqa: BLE001 —— 估算失败交由上层标注「营养数据暂不可用」
        logger.warning("estimate nutrition failed (recipe_id=%s): %s", recipe_id, exc)
        return empty


def _aggregate(session: Session, recipe_id: int, servings: int) -> dict:
    """执行营养聚合计算（函数）。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID。
        servings：份数。

    返回值：
        dict：估算结果结构（见 estimate_recipe_nutrition 返回值）。

    异常：
        查询异常向上抛出（由 estimate_recipe_nutrition 捕获转降级结构）。
    """
    from app.models import Ingredient  # 局部导入避免循环依赖

    rows = session.execute(
        select(RecipeIngredient, Ingredient.name, IngredientNutrition)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .join(
            IngredientNutrition,
            IngredientNutrition.ingredient_id == RecipeIngredient.ingredient_id,
            isouter=True,
        )
        .where(RecipeIngredient.recipe_id == recipe_id)
    ).all()

    total = {f: 0.0 for f in _NUTRIENT_FIELDS}
    excluded_items: list[str] = []
    has_any_data = False

    for ri, ing_name, nutrition in rows:
        grams = _resolve_grams(ri.amount_value, ri.amount_min, ri.amount_max, ri.amount_unit, ing_name)
        # 无营养行或关键字段缺失（kcal 为 None）→ 未纳入统计，不按 0 计
        if nutrition is None or nutrition.kcal_100g is None or grams is None:
            reason = "未纳入统计" if (nutrition is None or nutrition.kcal_100g is None) else "用量无法换算"
            excluded_items.append(f"{ing_name} {reason}")
            continue
        has_any_data = True
        factor = grams / 100.0
        total["kcal"] += float(nutrition.kcal_100g) * factor
        if nutrition.protein_g is not None:
            total["protein_g"] += float(nutrition.protein_g) * factor
        if nutrition.fat_g is not None:
            total["fat_g"] += float(nutrition.fat_g) * factor
        if nutrition.carbs_g is not None:
            total["carbs_g"] += float(nutrition.carbs_g) * factor
        if nutrition.sodium_mg is not None:
            total["sodium_mg"] += float(nutrition.sodium_mg) * factor

    if not has_any_data and not excluded_items:
        # 整谱无任何营养数据：全部主料标注
        excluded_items.append("全部食材 未纳入统计")

    rounded_total = {f: round(v, 1) for f, v in total.items()}
    per_serving = {f: round(v / servings, 1) for f, v in total.items()}
    return {
        "recipe_id": recipe_id,
        "servings": servings,
        "total": rounded_total,
        "per_serving": per_serving,
        "excluded_items": excluded_items,
        "estimate_note": ESTIMATE_NOTE,
    }


def estimate_nutrition_parallel(recipe_ids: list[int], servings: int = 2) -> dict[int, dict]:
    """并行估算多道菜谱营养（函数）。

    说明：
        供 node_nutrition 与排序并行消费；每个菜谱独立会话 + 线程池并行执行；
        单条失败不影响其余（失败的 recipe_id 不出现在结果中，由调用方标注降级）。

    参数：
        recipe_ids：菜谱 ID 列表。
        servings：份数。

    返回值：
        dict[int, dict]：{recipe_id: 估算结果}。

    异常：
        不抛出（单条失败仅告警日志）。
    """
    results: dict[int, dict] = {}

    def _one(rid: int) -> tuple[int, dict]:
        with SessionLocal() as s:
            return rid, estimate_recipe_nutrition(s, rid, servings)

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(recipe_ids)))) as pool:
        futures = [pool.submit(_one, rid) for rid in recipe_ids]
        for future in futures:
            try:
                rid, value = future.result(timeout=10)
                results[rid] = value
            except Exception as exc:  # noqa: BLE001 —— 并行估算单条失败不影响其余
                logger.warning("parallel nutrition estimate failed: %s", exc)
    return results
