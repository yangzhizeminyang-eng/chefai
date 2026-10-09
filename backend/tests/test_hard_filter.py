"""布尔硬过滤单元测试。

覆盖（spec Task 6.2 / D9 红线）：
    - 过敏原硬过滤：含致敏原菜谱过滤后数量 = 0（绝不降权，只排除）；
    - filtered_by['allergen'] 计数准确 = 候选中含致敏原菜谱数；
    - 排序函数输入集与过滤输出集完全一致（结构上无法给被过滤项打分）。
"""

from __future__ import annotations

from app.ability.ranking import hard_filter, weighted_rank
from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal
from app.safety.types import SafetyProfile


def _load_all_candidates() -> list[dict]:
    """加载全量已发布菜谱候选（函数）。

    说明：
        空食材 + 空文本 → 冷启动全量召回（retrieve_candidates 保证）。

    参数：
        无。

    返回值：
        list[dict]：候选菜谱字典列表。

    异常：
        数据库异常向上抛出（环境前置条件）。
    """
    with SessionLocal() as session:
        return retrieve_candidates(session, [], query_text=None, limit=200)


def test_allergen_hard_filter_excludes_all() -> None:
    """过敏原硬过滤：含蛋菜谱完全排除（函数）。

    说明：
        SafetyProfile(user_allergen_codes=['egg']) 过滤后：
        - 结果集中 allergen_codes / ingredient_allergen_codes 含 egg 的数量 = 0；
        - filtered_by['allergen'] 计数 = 候选中含蛋菜谱数；
        - 被过滤项确实存在（保证断言有效性，种子含蛋菜谱 ≥1）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = _load_all_candidates()
    assert candidates, "种子菜谱为空，请先执行 python -m app.seed"

    with SessionLocal() as session:
        filtered, counts = hard_filter(session, candidates, SafetyProfile(user_allergen_codes=["egg"]))

    # 过滤后集合中不允许任何含蛋菜谱（🔴 布尔排除，非降权）
    leaked = [
        c
        for c in filtered
        if "egg" in (c.get("allergen_codes") or []) or "egg" in (c.get("ingredient_allergen_codes") or [])
    ]
    assert leaked == []
    # 计数准确：= 候选中含蛋菜谱数
    expected = sum(
        1
        for c in candidates
        if "egg" in (c.get("allergen_codes") or []) or "egg" in (c.get("ingredient_allergen_codes") or [])
    )
    assert counts["allergen"] == expected
    # 种子必须含蛋菜谱（否则过滤断言无区分度）
    assert expected >= 1
    # 过滤后数量 = 候选总数 - 含蛋数（无其他过滤条件时）
    assert len(filtered) == len(candidates) - expected


def test_rank_input_equals_filter_output() -> None:
    """排序函数输入集与过滤输出集完全一致（函数）。

    说明：
        对过滤输出集打上唯一标记字段 _filter_marker 后传入 weighted_rank：
        排序输出全部携带该标记且 recipe_id 均属于过滤输出集——
        被过滤项根本未进入排序函数（结构防降权）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = _load_all_candidates()
    with SessionLocal() as session:
        filtered, _counts = hard_filter(session, candidates, SafetyProfile(user_allergen_codes=["egg"]))

    marked = [dict(c, _filter_marker="from_hard_filter") for c in filtered]
    ranked = weighted_rank(marked, SafetyProfile(), None)

    assert ranked, "排序输出不应为空"
    filtered_ids = {c["recipe_id"] for c in filtered}
    for item in ranked:
        assert item.get("_filter_marker") == "from_hard_filter"
        assert item["recipe_id"] in filtered_ids
