"""7 因子排序单元测试。

覆盖（spec Task 6.3）：
    - 每条结果 rank_reasons 至少 1 条（可解释性）；
    - 三档 match_level 划分正确（missing=0 → can_cook_now / 1~2 → missing_1_2 / ≥3 → need_more）；
    - Top 8 截断（spec：推荐数默认 ≤8 条）。
"""

from __future__ import annotations

from app.ability.ranking import TOP_N, weighted_rank
from app.safety.types import SafetyProfile


def _make_candidate(recipe_id: int, main_names: list[str], covered: list[str], difficulty: int = 2) -> dict:
    """构造排序候选字典（函数）。

    参数：
        recipe_id：菜谱 ID（唯一）。
        main_names：主料名列表。
        covered：用户已覆盖食材名列表。
        difficulty：难度值（1~5，默认 2）。

    返回值：
        dict：retrieve_candidates 兼容结构的候选字典。

    异常：
        无。
    """
    return {
        "recipe_id": recipe_id,
        "title": f"测试菜谱{recipe_id}",
        "difficulty": difficulty,
        "time_minutes": 15,
        "calories_kcal": 200,
        "allergen_codes": [],
        "ingredient_allergen_codes": [],
        "dietary_flags": [],
        "equipment": [],
        "covered_count": len([n for n in main_names if n in covered]),
        "covered_names": [n for n in main_names if n in covered],
        "main_ingredient_names": main_names,
        "seasoning_names": [],
        "matched_by_title": False,
    }


def test_rank_reasons_non_empty() -> None:
    """每条排序结果至少 1 条 rank_reasons（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = [
        _make_candidate(1, ["土豆", "青椒"], ["土豆", "青椒"]),
        _make_candidate(2, ["茄子", "蒜"], ["茄子"]),
        _make_candidate(3, ["冬瓜", "虾皮", "香菜", "紫菜"], ["冬瓜"]),
    ]
    ranked = weighted_rank(candidates, SafetyProfile(), None)
    assert ranked
    for item in ranked:
        assert item["rank_reasons"], f"recipe_id={item['recipe_id']} 缺少排序理由"
        assert all(isinstance(r, str) and r for r in item["rank_reasons"])


def test_match_level_partition() -> None:
    """三档 match_level 划分正确（函数）。

    说明：
        missing=0 → can_cook_now；missing 1~2 → missing_1_2；missing ≥3 → need_more。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = [
        _make_candidate(10, ["土豆", "青椒"], ["土豆", "青椒"]),   # missing=0
        _make_candidate(11, ["土豆", "青椒", "肉"], ["土豆"]),     # missing=2 → missing_1_2
        _make_candidate(12, ["冬瓜", "虾皮", "香菜", "紫菜"], ["冬瓜"]),  # missing=3 → need_more
        _make_candidate(13, ["番茄", "蛋"], ["番茄"]),             # missing=1 → missing_1_2
    ]
    ranked = weighted_rank(candidates, SafetyProfile(), None)
    level_by_id = {item["recipe_id"]: item["match_level"] for item in ranked}
    assert level_by_id[10] == "can_cook_now"
    assert level_by_id[11] == "missing_1_2"
    assert level_by_id[12] == "need_more"
    assert level_by_id[13] == "missing_1_2"


def test_top_n_truncation() -> None:
    """候选超过 TOP_N 时截断为 8 条（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = [_make_candidate(i, ["土豆"], ["土豆"]) for i in range(100, 112)]
    ranked = weighted_rank(candidates, SafetyProfile(), None)
    assert len(ranked) == TOP_N
    # 分数降序：输出有序（非严格降序断言，仅验证条数与去重）
    ids = [item["recipe_id"] for item in ranked]
    assert len(set(ids)) == TOP_N
