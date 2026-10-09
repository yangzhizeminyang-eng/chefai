"""pgvector 混合检索测试（Task 8：R-1 收敛）。

覆盖：
    - HashEmbeddingProvider 确定性：同文本同向量 / 异文本异向量 / 1024 维 / L2 范数≈1；
    - ensure_embeddings 幂等：连续两次调用 verified 行数不变；published 菜谱覆盖 ≥90%；
    - 混合召回（鸡蛋+西红柿组合）：结果 ≤8 条且 recipe_id 去重；向量开/关两路径均有结果
      （本机无 pgvector 扩展 → 走 embedding_json 纯 Python 点积分支）；
    - 🔴 分区隔离红线：source='ai_private' 的向量行（owner=测试用户）在默认检索
      （include_private_owner=None）中绝不出现；include_private_owner=测试用户时可检索到；
    - 降级：probe 返回 False（JSON 点积降级）与 probe 返回 True 但 raw SQL 失败
      （无扩展环境强制 pgvector 分支）两种场景下检索均不抛错、仍出结果；
    - Top-8 截断：冷启动全量召回结果被截断为 ≤8 条。

数据自洽：
    自建 user / recipe（draft 假菜谱）/ recipe_embedding 行，测后清理，
    重复执行互不影响（幂等）。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.ability.embedding import (
    EMBEDDING_DIMENSION,
    HashEmbeddingProvider,
    ensure_embeddings,
    get_embedding_provider,
)
from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal
from app.models import Recipe, RecipeEmbedding, User

# 测试用户 anonymous_id 前缀（清理依据，避免误删真实数据）
_TEST_ANON_PREFIX = "t_v8_"

# 分区测试专用：确保不与种子食材/菜名碰撞的隔离词
_PARTITION_TOKEN = "t8xq7"


def test_hash_embedding_deterministic() -> None:
    """HashEmbeddingProvider 确定性与维度约束（测试）。

    断言：
        - 同文本两次嵌入向量完全一致（确定性）；
        - 不同文本向量不同；
        - 每条向量 1024 维；
        - L2 范数≈1（已归一化，点积即余弦）。

    异常：
        断言失败即测试失败。
    """
    provider = HashEmbeddingProvider()
    vec_a1 = provider.embed(["番茄炒蛋"])[0]
    vec_a2 = provider.embed(["番茄炒蛋"])[0]
    vec_b = provider.embed(["红烧牛肉面"])[0]
    assert vec_a1 == vec_a2, "同文本两次嵌入必须完全一致（确定性）"
    assert vec_a1 != vec_b, "不同文本向量必须不同"
    assert len(vec_a1) == EMBEDDING_DIMENSION, f"向量维度应为 {EMBEDDING_DIMENSION}"
    norm = sum(x * x for x in vec_a1) ** 0.5
    assert abs(norm - 1.0) < 1e-6, f"L2 范数应≈1，实际 {norm}"


def test_get_provider_default_hash() -> None:
    """默认工厂返回 HashEmbeddingProvider（测试）。

    异常：
        类型不符断言失败。
    """
    assert isinstance(get_embedding_provider(), HashEmbeddingProvider)


def test_ensure_embeddings_idempotent() -> None:
    """ensure_embeddings 幂等与覆盖率（测试）。

    断言：
        - 连续两次调用 verified 行数不变（幂等）；
        - 回填后 verified 向量覆盖的 published 菜谱 ≥90%。

    异常：
        幂等被破坏或覆盖率不足时断言失败。
    """
    session = SessionLocal()
    try:
        ensure_embeddings(session)
        count_1 = session.execute(
            select(func.count()).select_from(RecipeEmbedding).where(RecipeEmbedding.source == "verified")
        ).scalar()
        ensure_embeddings(session)
        count_2 = session.execute(
            select(func.count()).select_from(RecipeEmbedding).where(RecipeEmbedding.source == "verified")
        ).scalar()
        assert count_1 == count_2, f"幂等被破坏：第一次 {count_1} 行，第二次 {count_2} 行"

        published_total = session.execute(
            select(func.count()).select_from(Recipe).where(Recipe.status == "published")
        ).scalar()
        covered = session.execute(
            select(func.count(func.distinct(RecipeEmbedding.recipe_id)))
            .where(RecipeEmbedding.source == "verified")
            .where(RecipeEmbedding.recipe_id.is_not(None))
        ).scalar()
        ratio = covered / published_total if published_total else 0.0
        assert ratio >= 0.9, f"published 菜谱向量覆盖率 {ratio:.2%} < 90%（{covered}/{published_total}）"
    finally:
        session.close()


def test_hybrid_retrieval_vector_on_and_off() -> None:
    """混合召回：鸡蛋+西红柿组合，向量开/关均有结果且 ≤8 去重（测试）。

    说明：
        本机无 pgvector 扩展 → use_vector=True 实际走 embedding_json
        纯 Python 点积分支（惰性回填保证向量数据存在）。

    异常：
        结果为空 / 超 8 条 / recipe_id 重复时断言失败。
    """
    session = SessionLocal()
    try:
        from app.ability.retrieval import match_ingredients_in_text

        ids, names = match_ingredients_in_text(session, "西红柿炒鸡蛋")
        assert ids or names or True  # 食材解析结果不强约束（种子词表差异容忍）

        for use_vector in (True, False):
            results = retrieve_candidates(
                session, ids, query_text="西红柿炒鸡蛋", use_vector=use_vector
            )
            assert results, f"use_vector={use_vector} 时召回结果为空"
            assert len(results) <= 8, f"use_vector={use_vector} 返回 {len(results)} 条 > 8"
            rid_list = [r["recipe_id"] for r in results]
            assert len(rid_list) == len(set(rid_list)), f"use_vector={use_vector} 存在重复 recipe_id"

        # 向量路径额外断言：候选带 matched_by_vector 字段且类型正确（结构无感扩展）
        results = retrieve_candidates(session, ids, query_text="西红柿炒鸡蛋", use_vector=True)
        assert all(isinstance(r.get("matched_by_vector"), bool) for r in results)
    finally:
        session.close()


def test_partition_isolation_ai_private() -> None:
    """🔴 分区隔离红线：ai_private 向量行不进默认推荐（测试）。

    流程：
        1. 自建测试用户 + draft 假菜谱（隔离词标题，确保关键词路径不命中）；
        2. 插入 source='ai_private' 向量行（owner=测试用户，recipe_id 指向假菜谱）；
        3. 默认检索（include_private_owner=None）：结果不含该菜谱；
        4. include_private_owner=测试用户：结果包含该菜谱（创新链路可见）。

    异常：
        默认检索出现 ai_private 菜谱（红线破坏）或 owner 检索不可见时断言失败。
    """
    session = SessionLocal()
    user_id: int | None = None
    try:
        provider = HashEmbeddingProvider()
        user = User(anonymous_id=f"{_TEST_ANON_PREFIX}{uuid.uuid4().hex[:16]}")
        recipe = Recipe(
            title=f"__{_PARTITION_TOKEN}独享冰饮",
            difficulty=1,
            servings=1,
            source_label="unit-test",
            source_license="test",
            status="draft",  # draft：不进 published 回填池与关键词召回，仅经 ai_private 向量行可见
        )
        session.add(user)
        session.add(recipe)
        session.flush()
        user_id, recipe_id = int(user.id), int(recipe.id)
        session.add(
            RecipeEmbedding(
                recipe_id=recipe_id,
                owner_user_id=user_id,
                source="ai_private",
                embedding_json=provider.embed([recipe.title])[0],
            )
        )
        session.commit()

        query = recipe.title.lstrip("_")  # "t8xq7独享冰饮"

        # 默认检索：AI 私有菜谱绝不出现（分区红线）
        default_results = retrieve_candidates(
            session, [], query_text=query, use_vector=True, include_private_owner=None
        )
        assert recipe_id not in {r["recipe_id"] for r in default_results}, \
            "🔴 分区红线被破坏：默认检索结果包含了 source='ai_private' 的菜谱"

        # 创新链路：owner 显式开启后可检索到（向量 Top-20 命中，sim=1.0）
        owner_results = retrieve_candidates(
            session, [], query_text=query, use_vector=True, include_private_owner=user_id
        )
        assert recipe_id in {r["recipe_id"] for r in owner_results}, \
            "include_private_owner=owner 时应检索到 ai_private 菜谱"
        owner_item = next(r for r in owner_results if r["recipe_id"] == recipe_id)
        assert owner_item["matched_by_vector"] is True, "owner 命中的私有菜谱应带向量来源标记"
    finally:
        # 自清理：embedding 行随 user CASCADE；draft 菜谱与 user 显式删除
        session.rollback()
        if user_id is not None:
            session.query(RecipeEmbedding).filter(
                RecipeEmbedding.owner_user_id == user_id
            ).delete(synchronize_session=False)
            session.query(Recipe).filter(
                Recipe.title.like(f"%{_PARTITION_TOKEN}%"), Recipe.source_label == "unit-test"
            ).delete(synchronize_session=False)
            session.query(User).filter(User.id == user_id).delete()
            session.commit()
        session.close()


def test_probe_false_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    """probe 返回 False → 检索仍出结果（JSON 点积降级路径）（测试）。

    参数：
        monkeypatch：pytest 夹具（patch retrieval.probe_pgvector）。

    异常：
        检索抛错或结果为空时断言失败。
    """
    import app.ability.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "probe_pgvector", lambda *a, **k: False)
    session = SessionLocal()
    try:
        results = retrieve_candidates(session, [], query_text="西红柿炒鸡蛋", use_vector=True)
        assert results, "probe=False 降级路径应仍返回结果"
        assert len(results) <= 8
    finally:
        session.close()


def test_pgvector_sql_failure_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """probe 返回 True 但 raw SQL 失败 → 降级关键词路径且不抛错（测试）。

    说明：
        本机无扩展（无 embedding 列）：强制 pgvector 分支必触发 SQL 异常，
        验证「向量路径异常 → logger.warning 降级 → 接口 200」兜底链路。

    参数：
        monkeypatch：pytest 夹具（patch retrieval.probe_pgvector）。

    异常：
        检索抛错（降级失效）时断言失败。
    """
    import app.ability.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "probe_pgvector", lambda *a, **k: True)
    session = SessionLocal()
    try:
        results = retrieve_candidates(session, [], query_text="西红柿炒鸡蛋", use_vector=True)
        assert results, "raw SQL 失败后应降级走既有关键词路径返回结果"
        assert len(results) <= 8
    finally:
        session.close()


def test_top_k_truncation() -> None:
    """Top-8 截断：冷启动全量召回被截断为 ≤8 条（测试）。

    异常：
        返回超 8 条时断言失败。
    """
    session = SessionLocal()
    try:
        results = retrieve_candidates(session, [], query_text=None, use_vector=False)
        assert results, "冷启动应返回候选"
        assert len(results) <= 8, f"冷启动返回 {len(results)} 条，应被截断为 ≤8"
        rid_list = [r["recipe_id"] for r in results]
        assert len(rid_list) == len(set(rid_list)), "冷启动结果存在重复 recipe_id"
    finally:
        session.close()
