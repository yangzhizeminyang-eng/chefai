"""检索文本信号回归测试（rt-005 修复，Task 2.2）。

背景（根因取证结论）：
    rt-005（"可乐鸡翅怎么做" → 期望 Top-5 命中"鸡翅"）在 hash 口径数据库检索
    Eval 中失败。白盒取证：
    ① 召回存在：match_ingredients_in_text("可乐鸡翅怎么做") 命中食材
       可乐(253)/鸡(1101)/别名鸡翅→鸡翅中(67)；引用 67 的已发布菜谱含
       recipe 10 可乐鸡翅——② 文本扩展路确实召回了 recipe 10。
    ② 排序信号丢失：covered_count 只统计「用户显式食材入参」命中（id_set），
       文本解析食材的引用数（text_rank_extra）仅 RRF 分支消费，fixed 分支
       完全不消费 → 空食材口径下全候选 covered_count=0，fixed 排序退化为
       向量相似度，hash 语义噪声候选（可乐桶等）占满 Top-8，recipe 10
       （_vector_sim=0）被挤出 Top-5（实测第 14 位）。
    ③ 菜名匹配方向缺陷：`title ILIKE '%整句查询%'` 要求菜名包含整个查询
       文本，"可乐鸡翅怎么做" 永远菜名不命中 title="可乐鸡翅"（正确方向
       应为查询文本包含菜名）。

覆盖：
    - rt-005 主用例：Top-5 内存在 title 含"鸡翅"的菜谱（修复前失败，Red）；
    - 相近表达防硬编码：别名/食材组合/做法后缀/变体食材五组问法（有种子
      语料支撑，断言口径与 Eval hit_at_k 一致：标题含关键词子串）；
    - 既有 17 条检索用例不回退：与 Eval Hit@5 同口径的逐条回归断言
      （数据集 retrieval_cases.jsonl 为准，不复制用例内容）。

数据依赖：
    开发库种子语料（recipe 10 等已发布菜谱、食材/别名表），与检索 Eval
    同一数据基础；EMBEDDING_PROVIDER 由 conftest 强制 hash（离线、确定性）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal

# 检索评测数据集路径（backend/eval/datasets/retrieval_cases.jsonl）
_RETRIEVAL_DATASET = (
    Path(__file__).resolve().parents[1] / "eval" / "datasets" / "retrieval_cases.jsonl"
)


def _top5_titles(query: str) -> list[str]:
    """执行一次默认口径检索并返回 Top-5 标题（内部辅助函数）。

    参数：
        query：自然语言查询文本。

    返回值：
        list[str]：检索 Top-5 候选标题（按检索排序）。

    异常：
        数据库不可达时向上抛出（测试失败）。
    """
    with SessionLocal() as session:
        candidates = retrieve_candidates(session, [], query)
    return [str(c.get("title") or "") for c in candidates[:5]]


def test_rt005_cola_chicken_top5() -> None:
    """rt-005 主回归：可乐鸡翅怎么做 Top-5 命中鸡翅（测试）。

    断言：
        "可乐鸡翅怎么做" 的 Top-5 候选标题中存在含"鸡翅"子串的菜谱
        （与 Eval hit_at_5 同口径；期望 title=可乐鸡翅 命中）。

    异常：
        Top-5 无"鸡翅"标题时断言失败（修复前的失败形态）。
    """
    titles = _top5_titles("可乐鸡翅怎么做")
    assert titles, "检索应返回候选"
    assert any("鸡翅" in t for t in titles), f"rt-005 回归失败：Top-5={titles}"


@pytest.mark.parametrize(
    ("query", "keyword"),
    [
        ("鸡翅怎么做", "翅"),
        ("用鸡翅和可乐做菜", "鸡翅"),
        ("可乐鸡翅的做法", "鸡翅"),
        ("鸡翅根怎么烧", "翅"),
        ("做可乐鸡翅用什么材料", "鸡翅"),
    ],
    ids=["alias", "combo", "howto-suffix", "variant-wing", "material-question"],
)
def test_rt005_near_expressions(query: str, keyword: str) -> None:
    """相近表达防硬编码：别名/组合/后缀/变体问法均命中翅类菜谱（测试）。

    说明：
        覆盖别名命中（鸡翅→鸡翅中）、食材组合（鸡翅+可乐）、做法后缀
        （的做法/怎么烧/什么材料）与变体食材（鸡翅根，语料无直接菜谱，
        经别名路径兜底），防止修复退化为针对 rt-005 单句的硬编码。

    参数：
        query：自然语言查询文本。
        keyword：期望 Top-5 标题包含的关键词子串。

    异常：
        Top-5 无命中标题时断言失败。
    """
    titles = _top5_titles(query)
    assert titles, f"{query} 检索应返回候选"
    assert any(keyword in t for t in titles), f"{query} Top-5 未含『{keyword}』：{titles}"


def test_retrieval_dataset_cases_no_regression() -> None:
    """既有 17 条检索用例 Hit@5 不回退（测试）。

    说明：
        以 eval/datasets/retrieval_cases.jsonl 为准逐条断言 Hit@5（标题含
        任一 expected_keyword，与 Eval 判定同口径）；rt-005 修复不得引入
        其他用例新增失败。

    异常：
        任一用例 Hit@5 未命中即断言失败（列出全部失败用例便于定位）。
    """
    lines = [
        line
        for line in _RETRIEVAL_DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith('{"dataset"')
    ]
    cases = [
        (obj["id"], obj["query"], obj["expected_keywords"])
        for obj in (json.loads(raw) for raw in lines)
    ]
    assert len(cases) >= 17, f"检索用例数异常：{len(cases)}"
    failures: list[str] = []
    for case_id, query, keywords in cases:
        titles = _top5_titles(query)
        if not any(any(kw in t for t in titles) for kw in keywords):
            failures.append(f"{case_id}({query}) Top-5={titles}")
    assert not failures, f"检索用例回归失败：{failures}"
