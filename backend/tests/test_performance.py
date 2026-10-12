"""性能冒烟断言测试（Task 12：测试与质量收尾）。

定位：
    性能冒烟断言，非基准测试（benchmark）。验证核心链路在 seed 后规模
    （~390 published 菜谱、300+ 候选）下满足响应预算。机器极端波动时
    允许单独 skip 本文件（如 pytest -k "not performance"）；选择直接
    硬断言路线，阈值放宽 20% 裕量已含（覆盖 CI 与本机波动），不引入
    pytest.mark.performance / addoption 机制。

阈值：
    全部集中定义于下方常量区，便于统一调整：
    - HARD_FILTER_MAX_SECONDS：SQL 布尔硬过滤（300+ 候选）≤ 0.5s；
    - WEIGHTED_RANK_MAX_SECONDS：7 因子加权排序（hard_filter 输出直传）≤ 1.0s；
    - HEALTHZ_MAX_SECONDS：GET /v1/healthz 健康检查 ≤ 0.5s；
    - RETRIEVAL_MAX_SECONDS：混合召回（含向量路径，预热后）≤ 2.0s。

环境前置：
    真实本地 PostgreSQL（aicook 库）且已执行 python -m app.seed。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ability.embedding import ensure_embeddings
from app.ability.ranking import hard_filter, weighted_rank
from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal
from app.graph.subgraphs import innovation as innovation_subgraph
from app.models import RecipeIngredient
from app.safety.types import SafetyProfile
from tests.test_innovation_degrade import _anon, _delete_user, _SlowLLMClient

# ---- 性能阈值（秒；已含 20% CI 波动裕量，直接硬断言）----
HARD_FILTER_MAX_SECONDS = 0.5    # spec 预算 500ms
WEIGHTED_RANK_MAX_SECONDS = 1.0  # spec 预算 1s
HEALTHZ_MAX_SECONDS = 0.5        # spec 预算 500ms
RETRIEVAL_MAX_SECONDS = 2.0      # spec 预算 2s
# P1 DEF-01：创新生成降级窗口——LLM 表达硬超时后模板降级必须在 30s 内返回
# （前端本接口专用 60s 超时，后端 25s 硬超时 + 降级拼装须留足余量；测试内打桩
# 将硬超时调小为 3s，替身阻塞 15s，故实际耗时 ≈3~4s，阈值取 30s 覆盖 CI 波动）
INNOVATION_DEGRADE_MAX_SECONDS = 30.0

# 候选规模下限（seed 后 ~390 published，取 300+ 留余量）
MIN_CANDIDATES = 300

# 混合召回中间池 / 最终返回条数（与生产默认口径一致）
_RETRIEVAL_LIMIT = 200
_RETRIEVAL_TOP_K = 8


@pytest.fixture(scope="module")
def large_candidates() -> list[dict]:
    """模块级大规模候选池（fixture）。

    说明：
        经 retrieve_candidates 冷启动回退分支一次召回全部 published 候选
        （limit/top_k 放宽到 500，seed 后 ~390 条），候选自带排序所需全部
        字段（recipe_id/difficulty/covered_count/main_ingredient_names 等），
        供 hard_filter 与 weighted_rank 计时测试共用。setup 中先幂等调用
        ensure_embeddings 完成预热（可能触发首次惰性回填与连接建立），
        确保后续向量检索计时不含一次性开销。

    返回值：
        list[dict]：候选字典列表（≥300 条，字段结构与生产检索输出一致）。

    异常：
        AssertionError：published 候选不足 300 条（环境前置条件，需先 python -m app.seed）。
    """
    with SessionLocal() as session:
        ensure_embeddings(session)  # 预热：幂等回填 + 嵌入单例/探测缓存就绪
        candidates = retrieve_candidates(
            session,
            [],
            None,
            limit=500,
            top_k=500,
            use_vector=False,
        )
    assert len(candidates) >= MIN_CANDIDATES, (
        f"published 候选仅 {len(candidates)} 条（需 ≥{MIN_CANDIDATES}），"
        "请先执行 python -m app.seed"
    )
    return candidates


def test_hard_filter_performance(large_candidates: list[dict]) -> None:
    """硬过滤性能断言（测试函数）：300+ 候选 hard_filter < 500ms。

    说明：
        SafetyProfile 带 egg 过敏原（与既有单测同口径，seed 中鸡蛋 → ["egg"]），
        对全量候选执行 SQL 布尔硬过滤并以 perf_counter 计时；同时取证
        filtered 计数字段完整、输出集是输入集子集（不破坏既有断言语义）。

    参数：
        large_candidates：模块级候选池 fixture（≥300 条）。

    返回值：
        None。

    异常：
        AssertionError：耗时超阈值或过滤结果结构异常。
    """
    profile = SafetyProfile(user_allergen_codes=["egg"])
    with SessionLocal() as session:
        start = time.perf_counter()
        filtered, counts = hard_filter(session, large_candidates, profile)
        elapsed = time.perf_counter() - start
    assert elapsed < HARD_FILTER_MAX_SECONDS, f"hard_filter took {elapsed:.3f}s"
    # 设备维度（equipment）为 M2/P6/S8 修复新增的过滤统计键
    assert set(counts) == {"allergen", "dietary_restriction", "difficulty", "equipment"}
    input_ids = {c["recipe_id"] for c in large_candidates}
    assert all(c["recipe_id"] in input_ids for c in filtered)


def test_weighted_rank_performance(large_candidates: list[dict]) -> None:
    """加权排序性能断言（测试函数）：hard_filter 输出直传 weighted_rank < 1s。

    说明：
        先经 hard_filter 得到过滤后候选（结构上保证 weighted_rank 只见
        过滤集合），再对其执行 7 因子排序并计时；ctx 带难度上限以覆盖
        difficulty 因子的完整计算路径，并取证 Top-8 与可解释字段结构。

    参数：
        large_candidates：模块级候选池 fixture（≥300 条）。

    返回值：
        None。

    异常：
        AssertionError：耗时超阈值或排序输出结构异常。
    """
    profile = SafetyProfile(user_allergen_codes=["egg"], difficulty_cap=3)
    with SessionLocal() as session:
        filtered, _counts = hard_filter(session, large_candidates, profile)
        assert filtered, "hard_filter 输出为空，无法构造排序输入"
        start = time.perf_counter()
        ranked = weighted_rank(filtered, ctx=profile)
        elapsed = time.perf_counter() - start
    assert elapsed < WEIGHTED_RANK_MAX_SECONDS, f"weighted_rank took {elapsed:.3f}s"
    assert 0 < len(ranked) <= 8  # Top-8 口径
    assert all("rank_score" in item and "rank_reasons" in item for item in ranked)


def test_healthz_performance(client: TestClient) -> None:
    """健康检查性能断言（测试函数）：GET /v1/healthz < 500ms。

    说明：
        conftest 的 client fixture 启动应用生命周期后，先做一次不计时的
        预热请求（排除首连/路由加载等一次性开销），再对第二次请求计时。

    参数：
        client：conftest 提供的 TestClient fixture。

    返回值：
        None。

    异常：
        AssertionError：状态码非 200 或耗时超阈值。
    """
    client.get("/v1/healthz")  # 预热：不计入计时
    start = time.perf_counter()
    response = client.get("/v1/healthz")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert elapsed < HEALTHZ_MAX_SECONDS, f"healthz took {elapsed:.3f}s"


def test_retrieve_candidates_performance() -> None:
    """混合召回性能断言（测试函数）：常见食材组合三路召回 < 2s。

    说明：
        预热阶段幂等调用 ensure_embeddings（首次惰性回填在此完成，不计时）；
        取引用菜谱数最多的 3 个食材作为「常见食材组合」，携带自然语言查询
        文本走覆盖 + 文本 + 向量三路混合召回，计时断言并取证输出结构。

    返回值：
        None。

    异常：
        AssertionError：耗时超阈值、食材引用为空或召回输出结构异常。
    """
    with SessionLocal() as session:
        ensure_embeddings(session)  # 预热：消除惰性回填对首次计时的污染
        hot_ids = [
            int(rid)
            for (rid,) in session.execute(
                select(RecipeIngredient.ingredient_id)
                .group_by(RecipeIngredient.ingredient_id)
                .order_by(func.count().desc())
                .limit(3)
            ).all()
        ]
        assert hot_ids, "ingredient 引用为空，请先执行 python -m app.seed"

        start = time.perf_counter()
        candidates = retrieve_candidates(
            session,
            hot_ids,
            "鸡蛋 番茄 家常快手菜",
            limit=_RETRIEVAL_LIMIT,
            top_k=_RETRIEVAL_TOP_K,
            use_vector=True,
        )
        elapsed = time.perf_counter() - start

    assert elapsed < RETRIEVAL_MAX_SECONDS, f"retrieve_candidates took {elapsed:.3f}s"
    assert 0 < len(candidates) <= _RETRIEVAL_TOP_K
    assert all("recipe_id" in c and "allergen_codes" in c for c in candidates)


def test_innovation_generate_degrade_budget(client: TestClient, monkeypatch) -> None:
    """创新生成降级路径总耗时断言（测试函数）：LLM 慢调用触发硬超时降级 ≤30s 且 ≤60s。

    说明：
        P1 DEF-01 配套性能断言。测试内打桩：将 LLM 硬超时调小为 3s、LLM 替身
        阻塞 15s（远超超时）→ 触发「硬超时 → 规则模板降级」路径；计时断言接口
        总耗时 ≤ INNOVATION_DEGRADE_MAX_SECONDS(30s)（降级窗口）且 ≤ 60s（前端
        专用超时预算），并取证降级来源 basis.generated_by == "template" 与响应
        结构完整（ok=true、is_ai_innovated=true）。风格与 test_innovation_degrade
        既有慢调用用例一致，替身与清理工具直接复用。

    参数：
        client：conftest 提供的 TestClient fixture。
        monkeypatch：pytest monkeypatch fixture。

    返回值：
        None。

    异常：
        AssertionError：状态码非 201、降级来源非 template 或耗时超阈值。
    """
    monkeypatch.setattr(innovation_subgraph, "LLM_HARD_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(innovation_subgraph, "get_llm_client", lambda: _SlowLLMClient(delay=15.0))

    anon = _anon()
    try:
        start = time.perf_counter()
        response = client.post(
            "/v1/innovation/generate",
            json={"ingredients": ["土豆", "青椒"]},
            headers={"X-Anonymous-Id": anon},
        )
        elapsed = time.perf_counter() - start
    finally:
        _delete_user(anon)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body.get("ok") is True
    recipe = body.get("recipe") or {}
    assert recipe.get("is_ai_innovated") is True
    assert (recipe.get("basis") or {}).get("generated_by") == "template"
    assert elapsed < INNOVATION_DEGRADE_MAX_SECONDS, (
        f"innovation degrade path took {elapsed:.2f}s (budget {INNOVATION_DEGRADE_MAX_SECONDS}s)"
    )
    assert elapsed < 60.0, f"innovation degrade path took {elapsed:.2f}s (frontend budget 60s)"
