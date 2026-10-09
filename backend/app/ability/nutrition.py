"""营养估算模块。

职责：
    按菜谱逐食材估算营养：食材营养（每 100g）× 克数 / 100 后聚合。
    - 克数规则：amount_value 且单位可换算（g/ml→1，勺→15，个→按 UNIT_GRAMS 兜底表，
      未收录取默认 50g）；amount_value 缺失时取 (amount_min + amount_max) / 2；
    - 无营养数据的食材列入 excluded_items 标「XX 未纳入统计」，🔴 不得按 0 计（spec D9）；
    - 返回总量与每份营养（随份数线性重算），固定标注「估算值，非实测值，误差约 ±15%」；
    - 热量口径统一（缺陷 M5/R4/S9）：唯一口径 = 每份 kcal（resolve_per_serving_kcal），
      数据流：DB calories_kcal（稳定来源）→ LLM 回退（校验通过后落定入库）→
      确定性回退（食材营养表求和 / 份数），保证同菜谱同输入多次请求结果一致。
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
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

# 每份 kcal 合理区间（M5/R4/S9）：DB 值 / LLM 回退值超出该区间视为无效数据
KCAL_PER_SERVING_MIN = 5.0
KCAL_PER_SERVING_MAX = 2000.0

# 每份 kcal 数据来源标注（随 resolve_per_serving_kcal 返回，写入响应 kcal_source 字段）
KCAL_SOURCE_SEED = "recipe_seed"
KCAL_SOURCE_LLM = "llm_estimate"
KCAL_SOURCE_FALLBACK = "deterministic_fallback"


def _is_valid_per_serving_kcal(value: float | None) -> bool:
    """校验每份 kcal 是否落在合理区间（函数）。

    说明：
        合理区间 [KCAL_PER_SERVING_MIN, KCAL_PER_SERVING_MAX]（默认 5~2000）；
        测试报告 observed 6.5 与 262 kcal/份同谱矛盾，6.5 即低于下限的无效样本。

    参数：
        value：待校验的每份 kcal 值（可 None）。

    返回值：
        bool：True = 有效（可采信）；False = 无效（须走确定性回退）。

    异常：
        无（非数值类型按无效处理）。
    """
    if value is None or isinstance(value, bool):
        return False
    try:
        return KCAL_PER_SERVING_MIN <= float(value) <= KCAL_PER_SERVING_MAX
    except (TypeError, ValueError):
        return False


def estimate_kcal_by_llm(recipe_title: str, servings: int) -> float | None:
    """LLM 回退估算每份热量（函数）。

    说明：
        仅在 DB calories_kcal 缺失时调用；未配置 LLM_API_KEY 时直接返回 None
        （零网络开销）；调用失败（LLMError）或输出非法（非数字 / 超出合理区间）
        均返回 None，由调用方落确定性回退；temperature=0 降低输出抖动。

    参数：
        recipe_title：菜名（LLM prompt 输入）。
        servings：份数（每份口径提示）。

    返回值：
        float | None：校验通过的每份 kcal（保留 1 位小数）；不可用时返回 None。

    异常：
        不抛出（一切 LLM/解析异常吞掉并告警日志，营养链路不阻断主流程）。
    """
    if not settings.LLM_API_KEY:
        return None
    try:
        # 局部导入避免模块加载顺序耦合（llm 客户端初始化依赖 settings）
        from app.ability.llm import get_llm_client

        result = get_llm_client().chat(
            system="你是营养估算助手。只输出一个数字，不要任何解释、单位或其他内容。",
            user=(
                f"请估算菜谱「{recipe_title}」（{servings} 人份）每份的热量，"
                f"单位 kcal，数值必须在 {KCAL_PER_SERVING_MIN:.0f}~{KCAL_PER_SERVING_MAX:.0f} 之间。"
            ),
            temperature=0,
        )
        match = re.search(r"\d+(?:\.\d+)?", result.content or "")
        if match is None:
            logger.warning("LLM kcal 输出无可解析数字（recipe=%s）: %r", recipe_title, result.content)
            return None
        value = round(float(match.group()), 1)
        if not _is_valid_per_serving_kcal(value):
            logger.warning(
                "LLM kcal 输出超出合理区间 [%s, %s]（recipe=%s）: %s",
                KCAL_PER_SERVING_MIN,
                KCAL_PER_SERVING_MAX,
                recipe_title,
                value,
            )
            return None
        return value
    except Exception as exc:  # noqa: BLE001 —— LLM 异常一律降级为 None（走确定性回退）
        logger.warning("LLM kcal estimate failed (recipe=%s): %s", recipe_title, exc)
        return None


def resolve_per_serving_kcal(session: Session, recipe: Recipe, servings: int) -> tuple[float | None, str]:
    """解析菜谱每份 kcal 的唯一口径（函数）。

    说明：
        数据流（M5/R4/S9 修复）：
        ① DB calories_kcal 存在且落在合理区间 → 直接采信（同输入恒定输出）；
        ② DB 缺失/无效 → LLM 回退估算，校验通过后落定写回 DB（commit），
           后续请求命中 ① 保证多次请求一致；
        ③ LLM 不可用/输出无效 → 确定性回退：食材营养表求和 / 份数（纯计算无随机）。

    参数：
        session：数据库会话（LLM 落定写回与确定性聚合共用）。
        recipe：菜谱 ORM 实例（读取/回写 calories_kcal）。
        servings：份数（确定性回退按此折算每份）。

    返回值：
        tuple[float | None, str]：(每份 kcal, 数据来源标注)；
        kcal 为 None 表示三种途径均不可用（前端按「未纳入统计」渲染）。

    异常：
        不抛出（聚合异常按 None 处理并告警）。
    """
    # ① DB 值优先：菜谱种子/管理员维护的稳定来源
    db_kcal = recipe.calories_kcal
    if db_kcal is not None and _is_valid_per_serving_kcal(float(db_kcal)):
        return float(db_kcal), KCAL_SOURCE_SEED
    if db_kcal is not None:
        logger.warning(
            "菜谱 %s 的 calories_kcal=%s 超出合理区间 [%s, %s]，转回退链",
            recipe.id, db_kcal, KCAL_PER_SERVING_MIN, KCAL_PER_SERVING_MAX,
        )

    # ② LLM 回退：采信前做区间二次校验（防御 LLM 实现/Mock 绕过内部校验），
    #    校验通过后落定写回 DB（后续请求直接命中 ①，消除输出随机性）
    llm_kcal = estimate_kcal_by_llm(str(recipe.title), int(servings))
    if llm_kcal is not None and _is_valid_per_serving_kcal(llm_kcal):
        try:
            recipe.calories_kcal = int(round(llm_kcal))
            session.commit()
        except Exception as exc:  # noqa: BLE001 —— 落定失败仅告警（本次请求仍返回 LLM 值）
            logger.warning("LLM kcal 落定写回失败（recipe=%s）: %s", recipe.id, exc)
            session.rollback()
        return llm_kcal, KCAL_SOURCE_LLM

    # ③ 确定性回退：食材营养表求和 / 份数（estimate_recipe_nutrition 纯 DB 计算，无随机源）
    try:
        estimate = _aggregate(session, int(recipe.id), max(1, int(servings)))
        fallback_kcal = float((estimate.get("per_serving") or {}).get("kcal") or 0.0)
        if fallback_kcal > 0:
            return round(fallback_kcal, 1), KCAL_SOURCE_FALLBACK
    except Exception as exc:  # noqa: BLE001 —— 聚合异常按未纳入处理
        logger.warning("确定性 kcal 回退失败（recipe=%s）: %s", recipe.id, exc)
    return None, KCAL_SOURCE_FALLBACK


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
