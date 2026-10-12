"""缺料质量单测（DEF-04 脏数据过滤 + DEF-12 缺料上限）。

覆盖：
    - DEF-04：is_valid_ingredient_name 纯函数各形态判定（空/纯数字/符号 → 无效，
      正常中文名/中英混合 → 有效）；weighted_rank 生成 missing_ingredients 时
      过滤无名/纯数字脏项，match_level 按过滤后口径判定（脏项剔除后可升档）；
    - DEF-12：「需要多买几样」档位在档内截断前排除 missing 数量 >8 的菜谱
      （低质候选整条不进结果、不占 Top 8 名额）；missing == 8 的菜谱保留。
"""

from __future__ import annotations

from app.ability.ranking import MAX_MISSING_INGREDIENTS, is_valid_ingredient_name, weighted_rank
from app.safety.types import SafetyProfile


def _make_candidate(recipe_id: int, main_names: list[str], covered: list[str], difficulty: int = 2) -> dict:
    """构造排序候选字典（函数，与 test_ranking.py 同款结构）。

    参数：
        recipe_id：菜谱 ID（唯一）。
        main_names：主料名列表（可含脏名，用于构造脏数据场景）。
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


# ---------------------------------------------------------------------------
# DEF-04：is_valid_ingredient_name 纯函数
# ---------------------------------------------------------------------------


def test_is_valid_ingredient_name() -> None:
    """脏名判定各形态：空/纯数字/符号无效，正常名称有效（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 有效：正常中文名 / 中英混合 / 英文
    assert is_valid_ingredient_name("鸡腿")
    assert is_valid_ingredient_name("郫县红油豆瓣酱")
    assert is_valid_ingredient_name("A4纸")
    assert is_valid_ingredient_name("Salt")
    # 无效：空串 / 纯空白 / 纯数字 / 纯符号 / None / 非字符串数字
    assert not is_valid_ingredient_name("")
    assert not is_valid_ingredient_name("   ")
    assert not is_valid_ingredient_name("1")
    assert not is_valid_ingredient_name("32")
    assert not is_valid_ingredient_name("1000")
    assert not is_valid_ingredient_name("<")
    assert not is_valid_ingredient_name("1.5")
    assert not is_valid_ingredient_name(None)
    assert not is_valid_ingredient_name(1)


def test_weighted_rank_filters_dirty_missing() -> None:
    """missing 生成处过滤脏项：无名/纯数字不入 missing_ingredients（函数）。

    说明：
        复刻「干煸仔鸡」脏数据形态（ingredient 表存在 name='1' 的 main 配料行）：
        候选主料含 '1'/''/'  '/'<' 时，排序输出的 missing_ingredients 只保留
        有效名，且 match_level 按过滤后口径判定（脏项不计入差 1–2 样的计数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = [
        _make_candidate(301, ["1", "", "  ", "<", "鸡腿"], []),
        _make_candidate(302, ["1", "鸡腿"], ["鸡腿"]),
    ]
    ranked = weighted_rank(candidates, SafetyProfile(), None)
    by_id = {item["recipe_id"]: item for item in ranked}

    # 301：脏项全剔除 → missing 只剩「鸡腿」→ 差 1 样档
    assert by_id[301]["missing_ingredients"] == ["鸡腿"]
    assert by_id[301]["match_level"] == "missing_1_2"
    # 302：脏项剔除后 missing==0 → 升档「现在就能做」（脏项不再压低覆盖率口径）
    assert by_id[302]["missing_ingredients"] == []
    assert by_id[302]["match_level"] == "can_cook_now"


# ---------------------------------------------------------------------------
# DEF-12：需要多买几样档位缺料上限
# ---------------------------------------------------------------------------


def test_weighted_rank_excludes_missing_over_limit() -> None:
    """missing 9 样的菜谱整条跳过，不进结果也不占 Top 8 名额（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    over = [f"食材{i}" for i in range(9)]  # 9 样缺料（> MAX_MISSING_INGREDIENTS）
    candidates = [
        _make_candidate(401, over, []),
        _make_candidate(402, ["鸡腿", "土豆"], []),
    ]
    ranked = weighted_rank(candidates, SafetyProfile(), None)
    ids = [item["recipe_id"] for item in ranked]
    assert 401 not in ids, "缺料 >8 样的低质推荐不应进入结果"
    assert 402 in ids, "正常候选不受上限过滤影响"


def test_weighted_rank_keeps_missing_at_limit() -> None:
    """missing 恰为 8 样的菜谱保留在「需要多买几样」档（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    at_limit = [f"食材{i}" for i in range(MAX_MISSING_INGREDIENTS)]  # 恰 8 样
    candidates = [_make_candidate(501, at_limit, [])]
    ranked = weighted_rank(candidates, SafetyProfile(), None)
    assert len(ranked) == 1
    assert ranked[0]["recipe_id"] == 501
    assert ranked[0]["match_level"] == "need_more"
    assert len(ranked[0]["missing_ingredients"]) == MAX_MISSING_INGREDIENTS
