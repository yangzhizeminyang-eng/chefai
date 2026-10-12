"""百炼嵌入提供方与检索融合测试（Task 7：向量模型升级）。

覆盖范围：
    - BailianEmbeddingProvider 单元（fake client 注入，绝不访问真实百炼 API）：
      分批请求与 L2 归一化 / 维度守卫（返回维度≠1024 抛 EmbeddingUnavailableError）/
      API 异常统一包装 / 空输入短路（不发起请求）/ 模块级 LRU 缓存命中 /
      space_name 取 settings.EMBEDDING_MODEL_NAME / 四项配置全空抛
      EmbeddingUnavailableError；
    - AC-08 嵌入空间隔离（GAP-4）：检索按 provider.space_name 过滤
      recipe_embedding.embedding_model，跨空间向量绝不通算余弦；
    - AC-09 合成查询开关（C4）：RETRIEVAL_VECTOR_FOR_INGREDIENTS=on 时按传入
      食材 id 顺序空格拼接查询文本，off 时嵌入提供方零调用；
    - AC-10 RRF 融合（C5）：RETRIEVAL_FUSION=rrf 候选携带 _fusion_ranks 内部键
      且重复调用排序稳定，fixed 缺省模式不含该键；
    - AC-11 CLI build_embeddings：增量回填幂等（连续两次行数不变）；
      --rebuild 仅删除目标空间（hash-v1）verified 行，其他嵌入空间行不被触碰。

数据自洽：
    直连本地 PostgreSQL（SessionLocal），自建 user/recipe/ingredient/
    recipe_embedding 行（隔离词 tbq9z / 匿名前缀 t_bail_），finally 彻底清理，
    可重复执行；不 mock 数据库；不访问真实百炼 API（fake client 与
    monkeypatch 注入，pytest 结束自动还原 settings）。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.ability.embedding import (
    BailianEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    HashEmbeddingProvider,
)
from app.ability.retrieval import retrieve_candidates
from app.cli import main
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Ingredient, Recipe, RecipeEmbedding, User

# 测试用户 anonymous_id 前缀（清理依据，避免误删真实数据）
_TEST_ANON_PREFIX = "t_bail_"

# 隔离词：自建菜谱标题/食材名专用，确保不与种子数据碰撞
_PARTITION_TOKEN = "tbq9z"


class _FakeEmbeddings:
    """伪 OpenAI embeddings 接口（模型类）：记录 create 调用并返回可配置的未归一化向量。

    说明：
        - 每条返回向量 = 全局序号位置上的 one-hot × 2.0（未归一化），
          可同时验证「响应按 index 对齐」与「L2 归一化」；
        - data 列表乱序返回，强制验证实现按响应 index 对齐而非依赖响应顺序；
        - error 非空时 create 抛出该异常（模拟网络/服务端故障）。

    属性：
        calls：每次 create 的关键字参数记录（model/input/dimensions/encoding_format）。
        dim：返回向量维度（默认 1024；512 用于维度守卫用例）。
        error：create 抛出的异常（None 表示正常返回）。
    """

    def __init__(self, dim: int = 1024, error: Exception | None = None) -> None:
        """构造函数（函数）。

        参数：
            dim：返回向量维度。
            error：create 调用时抛出的异常；None 表示正常返回。

        返回值：
            None。

        异常：
            无。
        """
        self.calls: list[dict] = []
        self.dim = dim
        self.error = error
        self._seq = 0

    def create(
        self, *, model: str, input: list[str], dimensions: int, encoding_format: str
    ) -> SimpleNamespace:
        """伪 embeddings.create（函数）：记录调用参数并返回伪响应。

        参数：
            model：模型名（应等于 provider.space_name）。
            input：本批文本列表。
            dimensions：请求维度（应恒为 1024）。
            encoding_format：编码格式（应恒为 "float"）。

        返回值：
            SimpleNamespace：含 data=[{index, embedding}] 的伪响应（data 乱序排列）。

        异常：
            self.error 非空时原样抛出（模拟百炼 API 故障）。
        """
        self.calls.append(
            {
                "model": model,
                "input": list(input),
                "dimensions": dimensions,
                "encoding_format": encoding_format,
            }
        )
        if self.error is not None:
            raise self.error
        data = []
        for i in range(len(input)):
            seq = self._seq
            self._seq += 1
            embedding = [2.0 if j == seq % self.dim else 0.0 for j in range(self.dim)]
            data.append(SimpleNamespace(index=i, embedding=embedding))
        data.reverse()  # 乱序返回：验证实现按 index 对齐
        return SimpleNamespace(data=data)


class _FakeClient:
    """伪 OpenAI 客户端（模型类）：仅承载 embeddings 接口，供替换 provider._client 注入。"""

    def __init__(self, api: _FakeEmbeddings) -> None:
        """构造函数（函数）。

        参数：
            api：伪 embeddings 接口实例。

        返回值：
            None。

        异常：
            无。
        """
        self.embeddings = api


class _FakeProvider(EmbeddingProvider):
    """检索层注入用伪嵌入提供方（模型类）：space_name 可指定，embed 返回预存向量并记录调用。"""

    def __init__(self, space_name: str, vectors: list[list[float]]) -> None:
        """构造函数（函数）。

        参数：
            space_name：嵌入空间标识（成为检索层 embedding_model 列的过滤条件）。
            vectors：预存归一化向量列表（embed 每次调用返回其拷贝复用）。

        返回值：
            None。

        异常：
            无。
        """
        self.space_name = space_name
        self._vectors = [list(v) for v in vectors]
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量伪嵌入（函数）：记录收到的文本并返回预存向量拷贝。

        参数：
            texts：待嵌入文本列表。

        返回值：
            list[list[float]]：预存向量的拷贝列表（供检索层点积复用）。

        异常：
            无。
        """
        self.calls.append(list(texts))
        return [list(v) for v in self._vectors]


@pytest.fixture(autouse=True)
def _clean_embedding_cache():
    """每个用例前后清空模块级查询嵌入 LRU 缓存（函数）。

    说明：
        BailianEmbeddingProvider 的缓存为模块级共享，残留会使「重复执行」与
        「缓存命中」断言失真，故 autouse 全量清空。

    返回值：
        None（yield 前后各清空一次）。

    异常：
        无。
    """
    from app.ability import embedding as emb_mod

    emb_mod._embed_cache.clear()
    yield
    emb_mod._embed_cache.clear()


@pytest.fixture()
def bailian_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """百炼离线配置 fixture（函数）：BASE/KEY 指向假地址，测试结束自动还原。

    说明：
        仅保证 BailianEmbeddingProvider 构造通过（配置非空）；真实请求由
        fake client 替换 provider._client 拦截，绝不联网。

    参数：
        monkeypatch：pytest 夹具（patch settings 属性）。

    返回值：
        None。

    异常：
        无。
    """
    monkeypatch.setattr(settings, "EMBEDDING_API_BASE", "https://bailian.test.example/compatible-mode/v1")
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "sk-test-bailian-offline")


def test_bailian_batch_and_normalize(monkeypatch: pytest.MonkeyPatch, bailian_env: None) -> None:
    """百炼嵌入分批请求与 L2 归一化（测试）。

    断言：
        - 3 条文本、batch=2 → 恰好 2 次 create 调用，input 按输入顺序切分；
        - create 收到 dimensions=1024、model=space_name、encoding_format="float"；
        - 返回 3 条、每条 1024 维、L2 范数≈1（输入未归一化全 2.0 one-hot）；
        - 响应 data 乱序返回时结果仍按输入顺序对齐（第 i 条向量峰值在第 i 维）。

    参数：
        monkeypatch：pytest 夹具（patch settings.EMBEDDING_BATCH_SIZE）。
        bailian_env：百炼离线配置夹具。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 2)
    provider = BailianEmbeddingProvider()
    api = _FakeEmbeddings()
    provider._client = _FakeClient(api)

    texts = ["百炼批甲", "百炼批乙", "百炼批丙"]
    vectors = provider.embed(texts)

    assert len(api.calls) == 2, "3 条文本 × batch=2 应恰好 2 次请求"
    assert api.calls[0]["input"] == texts[:2], "第一批应为前 2 条（按输入顺序）"
    assert api.calls[1]["input"] == texts[2:], "第二批应为剩余 1 条"
    assert api.calls[0]["model"] == provider.space_name, "model 参数应等于 space_name"
    assert api.calls[0]["dimensions"] == 1024, "dimensions 参数应恒为 1024"
    assert api.calls[0]["encoding_format"] == "float", "encoding_format 应恒为 float"

    assert len(vectors) == 3, "返回条数应与输入等长"
    for i, vec in enumerate(vectors):
        assert len(vec) == 1024, f"第 {i} 条应为 1024 维"
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-9, f"第 {i} 条 L2 范数应≈1，实际 {norm}"
        peak = max(range(len(vec)), key=lambda j: vec[j])
        assert peak == i, f"第 {i} 条结果应与输入第 {i} 条对齐（乱序响应仍按 index 对齐）"
        assert abs(sum(vec) - 1.0) < 1e-9, "one-hot 归一化后其余维度应≈0"


def test_bailian_dimension_guard(monkeypatch: pytest.MonkeyPatch, bailian_env: None) -> None:
    """维度守卫：返回向量维度≠1024 时抛 EmbeddingUnavailableError（测试）。

    参数：
        monkeypatch：pytest 夹具（占位，保持签名一致）。
        bailian_env：百炼离线配置夹具。

    异常：
        未抛 EmbeddingUnavailableError（守卫失效）时断言失败。
    """
    provider = BailianEmbeddingProvider()
    api = _FakeEmbeddings(dim=512)
    provider._client = _FakeClient(api)

    with pytest.raises(EmbeddingUnavailableError):
        provider.embed(["维度守卫探针"])
    assert len(api.calls) == 1, "异常前应确实发起过 1 次请求"


def test_bailian_api_error(monkeypatch: pytest.MonkeyPatch, bailian_env: None) -> None:
    """API 异常包装：create 抛 RuntimeError 时统一包装为 EmbeddingUnavailableError（测试）。

    参数：
        monkeypatch：pytest 夹具（占位，保持签名一致）。
        bailian_env：百炼离线配置夹具。

    异常：
        未抛 EmbeddingUnavailableError（包装失效）时断言失败。
    """
    provider = BailianEmbeddingProvider()
    api = _FakeEmbeddings(error=RuntimeError("模拟网络断开"))
    provider._client = _FakeClient(api)

    with pytest.raises(EmbeddingUnavailableError):
        provider.embed(["异常包装探针"])
    assert len(api.calls) == 1, "异常前应确实发起过 1 次请求"


def test_bailian_empty_input(monkeypatch: pytest.MonkeyPatch, bailian_env: None) -> None:
    """空输入短路：embed([]) 返回 [] 且不发起任何请求（测试）。

    参数：
        monkeypatch：pytest 夹具（占位，保持签名一致）。
        bailian_env：百炼离线配置夹具。

    异常：
        返回非空或发起请求时断言失败。
    """
    provider = BailianEmbeddingProvider()
    api = _FakeEmbeddings()
    provider._client = _FakeClient(api)

    assert provider.embed([]) == [], "空输入应返回空列表"
    assert api.calls == [], "空输入不应发起任何 create 请求"


def test_bailian_cache_hit(monkeypatch: pytest.MonkeyPatch, bailian_env: None) -> None:
    """模块级 LRU 缓存命中：同文本第二次 embed 不再请求，异文本才发新请求（测试）。

    参数：
        monkeypatch：pytest 夹具（占位，保持签名一致）。
        bailian_env：百炼离线配置夹具。

    异常：
        缓存未命中（重复请求）或两次结果不一致时断言失败。
    """
    provider = BailianEmbeddingProvider()
    api = _FakeEmbeddings()
    provider._client = _FakeClient(api)

    first = provider.embed(["百炼缓存探针"])
    second = provider.embed(["百炼缓存探针"])
    assert len(api.calls) == 1, "同文本第二次 embed 应命中缓存，不再请求"
    assert first == second, "缓存命中返回应与首次结果一致"

    provider.embed(["另一条不同文本"])
    assert len(api.calls) == 2, "不同文本应发起新请求（共 2 次）"
    assert api.calls[1]["input"] == ["另一条不同文本"]


def test_bailian_space_name(monkeypatch: pytest.MonkeyPatch, bailian_env: None) -> None:
    """嵌入空间标识：provider.space_name 取 settings.EMBEDDING_MODEL_NAME（测试）。

    参数：
        monkeypatch：pytest 夹具（patch settings.EMBEDDING_MODEL_NAME）。
        bailian_env：百炼离线配置夹具。

    异常：
        space_name 与配置不符时断言失败。
    """
    monkeypatch.setattr(settings, "EMBEDDING_MODEL_NAME", "qwen3.7-text-embedding-test")
    provider = BailianEmbeddingProvider()
    assert provider.space_name == "qwen3.7-text-embedding-test", "space_name 应取配置的模型名"
    assert provider.space_name == settings.EMBEDDING_MODEL_NAME, "space_name 应等于 EMBEDDING_MODEL_NAME"


def test_bailian_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置缺失：BASE/KEY 与 VISION 回落项均为空串时构造抛 EmbeddingUnavailableError（测试）。

    参数：
        monkeypatch：pytest 夹具（patch 四项配置为空串）。

    异常：
        构造未抛 EmbeddingUnavailableError 时断言失败。
    """
    for field in ("EMBEDDING_API_BASE", "EMBEDDING_API_KEY", "VISION_BASE_URL", "VISION_API_KEY"):
        monkeypatch.setattr(settings, field, "")
    with pytest.raises(EmbeddingUnavailableError):
        BailianEmbeddingProvider()


def test_space_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-08 嵌入空间隔离：跨空间向量行绝不被对方空间的检索命中（测试）。

    流程：
        1. 自建 user + 两个 draft 假菜谱（隔离词标题，不进关键词召回）；
        2. 行 A（fake-v1 空间，向量=embed(["tbq9zfake"])）挂菜谱甲；
           行 B（hash-v1 空间，向量=embed([菜谱乙标题])）挂菜谱乙；
        3. FakeProvider(space_name="fake-v1") 检索：只命中菜谱甲（matched_by_vector），
           菜谱乙（hash-v1 行）绝不出现；
        4. FakeProvider(space_name="hash-v1") 检索：只命中菜谱乙，菜谱甲绝不出现。

    参数：
        monkeypatch：pytest 夹具（注入 FakeProvider / 关闭回填与 pgvector）。

    异常：
        跨空间行被命中（隔离破坏）或目标空间未命中时断言失败。
    """
    import app.ability.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "lazy_backfill", lambda session: None)
    monkeypatch.setattr(retrieval_mod, "probe_pgvector", lambda *a, **k: False)
    hash_provider = HashEmbeddingProvider()

    session = SessionLocal()
    user_id: int | None = None
    recipe_ids: list[int] = []
    try:
        user = User(anonymous_id=f"{_TEST_ANON_PREFIX}{uuid.uuid4().hex[:16]}")
        title_a = f"__{_PARTITION_TOKEN}独享冰饮{uuid.uuid4().hex[:6]}"
        title_b = f"__{_PARTITION_TOKEN}独享炖菜{uuid.uuid4().hex[:6]}"
        recipe_a = Recipe(
            title=title_a, difficulty=1, servings=1,
            source_label="unit-test", source_license="test", status="draft",
        )
        recipe_b = Recipe(
            title=title_b, difficulty=1, servings=1,
            source_label="unit-test", source_license="test", status="draft",
        )
        session.add_all([user, recipe_a, recipe_b])
        session.flush()
        user_id = int(user.id)
        recipe_ids = [int(recipe_a.id), int(recipe_b.id)]
        session.add(
            RecipeEmbedding(
                recipe_id=recipe_ids[0], owner_user_id=user_id, source="ai_private",
                embedding_json=hash_provider.embed(["tbq9zfake"])[0], embedding_model="fake-v1",
            )
        )
        session.add(
            RecipeEmbedding(
                recipe_id=recipe_ids[1], owner_user_id=user_id, source="ai_private",
                embedding_json=hash_provider.embed([title_b.lstrip("_")])[0], embedding_model="hash-v1",
            )
        )
        session.commit()

        # 场景一：fake-v1 空间查询 → 只命中行 A（菜谱甲），hash-v1 的行 B 不可见
        fake_v1 = _FakeProvider("fake-v1", vectors=[hash_provider.embed(["tbq9zfake"])[0]])
        monkeypatch.setattr(retrieval_mod, "get_embedding_provider", lambda: fake_v1)
        results_a = retrieve_candidates(
            session, [], query_text=title_a.lstrip("_"), use_vector=True,
            include_private_owner=user_id,
        )
        hit_a = {r["recipe_id"] for r in results_a}
        assert recipe_ids[0] in hit_a, "fake-v1 空间检索应命中行 A 的菜谱甲"
        item_a = next(r for r in results_a if r["recipe_id"] == recipe_ids[0])
        assert item_a["matched_by_vector"] is True, "命中的私有菜谱应带向量来源标记"
        assert recipe_ids[1] not in hit_a, "🔴 空间隔离被破坏：hash-v1 的行 B 不应被 fake-v1 查询命中"

        # 场景二：hash-v1 空间查询 → 只命中行 B（菜谱乙），fake-v1 的行 A 不可见
        hash_space = _FakeProvider("hash-v1", vectors=[hash_provider.embed([title_b.lstrip("_")])[0]])
        monkeypatch.setattr(retrieval_mod, "get_embedding_provider", lambda: hash_space)
        results_b = retrieve_candidates(
            session, [], query_text=title_b.lstrip("_"), use_vector=True,
            include_private_owner=user_id,
        )
        hit_b = {r["recipe_id"] for r in results_b}
        assert recipe_ids[1] in hit_b, "hash-v1 空间检索应命中行 B 的菜谱乙"
        assert recipe_ids[0] not in hit_b, "🔴 空间隔离被破坏：fake-v1 的行 A 不应被 hash-v1 查询命中"
    finally:
        # 自清理：embedding 行随 user CASCADE，仍显式删除；draft 菜谱与 user 删除
        session.rollback()
        if user_id is not None:
            session.query(RecipeEmbedding).filter(
                RecipeEmbedding.owner_user_id == user_id
            ).delete(synchronize_session=False)
            if recipe_ids:
                session.query(Recipe).filter(Recipe.id.in_(recipe_ids)).delete(synchronize_session=False)
            # 兜底：清理同源隔离词的残留菜谱（防历史残留干扰重复执行）
            session.query(Recipe).filter(
                Recipe.title.like(f"%{_PARTITION_TOKEN}%"), Recipe.source_label == "unit-test"
            ).delete(synchronize_session=False)
            session.query(User).filter(User.id == user_id).delete()
            session.commit()
        session.close()


def test_synthetic_query_on_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-09 合成查询开关：on 时按食材 id 顺序拼接文本，off 时零调用（测试）。

    流程：
        1. 自建两个隔离词食材（tbq9zA/tbq9zB + uuid 后缀防碰撞）；
        2. RETRIEVAL_VECTOR_FOR_INGREDIENTS=on：retrieve_candidates(query_text=None)
           → FakeProvider 恰好收到一次 ["tbq9zA... tbq9zB..."]（按传入 id 顺序）；
        3. 开关 off：同调用 → FakeProvider 零调用。

    参数：
        monkeypatch：pytest 夹具（注入 FakeProvider / 开关 / 关闭回填与 pgvector）。

    异常：
        合成文本错误、顺序错乱或 off 时仍调用嵌入方时断言失败。
    """
    import app.ability.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "lazy_backfill", lambda session: None)
    monkeypatch.setattr(retrieval_mod, "probe_pgvector", lambda *a, **k: False)
    hash_provider = HashEmbeddingProvider()

    session = SessionLocal()
    ingredient_ids: list[int] = []
    try:
        suffix = uuid.uuid4().hex[:8]
        name_a = f"tbq9zA{suffix}"
        name_b = f"tbq9zB{suffix}"
        ing_a = Ingredient(name=name_a, category="veg")
        ing_b = Ingredient(name=name_b, category="veg")
        session.add_all([ing_a, ing_b])
        session.flush()
        ingredient_ids = [int(ing_a.id), int(ing_b.id)]
        session.commit()

        expected_query = f"{name_a} {name_b}"
        fake = _FakeProvider("hash-v1", vectors=[hash_provider.embed([expected_query])[0]])
        monkeypatch.setattr(retrieval_mod, "get_embedding_provider", lambda: fake)

        monkeypatch.setattr(settings, "RETRIEVAL_VECTOR_FOR_INGREDIENTS", "on")
        retrieve_candidates(session, ingredient_ids, query_text=None, use_vector=True)
        assert fake.calls == [[expected_query]], (
            f"on 时应按传入食材 id 顺序合成一次查询，实际 {fake.calls}"
        )

        fake.calls.clear()
        monkeypatch.setattr(settings, "RETRIEVAL_VECTOR_FOR_INGREDIENTS", "off")
        retrieve_candidates(session, ingredient_ids, query_text=None, use_vector=True)
        assert fake.calls == [], "off 时合成查询关闭，嵌入提供方不应被调用"
    finally:
        session.rollback()
        if ingredient_ids:
            session.query(Ingredient).filter(
                Ingredient.id.in_(ingredient_ids)
            ).delete(synchronize_session=False)
        # 兜底：清理隔离词残留食材（种子食材均为中文，绝不以 tbq9z 开头）
        session.query(Ingredient).filter(
            Ingredient.name.like(f"{_PARTITION_TOKEN}%")
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_rrf_fusion(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-10 RRF 融合：rrf 候选带 _fusion_ranks 且排序稳定，fixed 模式无该键（测试）。

    参数：
        monkeypatch：pytest 夹具（patch RETRIEVAL_FUSION / 关闭回填与 pgvector）。

    异常：
        rrf 结果为空/超 8 条/排序不稳定/缺 _fusion_ranks，或 fixed 模式残留该键时
        断言失败。
    """
    import app.ability.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "lazy_backfill", lambda session: None)
    monkeypatch.setattr(retrieval_mod, "probe_pgvector", lambda *a, **k: False)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")

    session = SessionLocal()
    try:
        monkeypatch.setattr(settings, "RETRIEVAL_FUSION", "rrf")
        results_1 = retrieve_candidates(session, [], query_text="西红柿炒鸡蛋", use_vector=True)
        assert 0 < len(results_1) <= 8, f"rrf 结果应非空且 ≤8，实际 {len(results_1)}"
        results_2 = retrieve_candidates(session, [], query_text="西红柿炒鸡蛋", use_vector=True)
        assert [r["recipe_id"] for r in results_1] == [r["recipe_id"] for r in results_2], (
            "rrf 排序应确定：重复调用两次 recipe_id 顺序完全一致"
        )
        assert all(isinstance(r.get("_fusion_ranks"), dict) for r in results_1), (
            "rrf 模式每个候选应携带 _fusion_ranks 内部键且值为 dict"
        )

        monkeypatch.setattr(settings, "RETRIEVAL_FUSION", "fixed")
        results_fixed = retrieve_candidates(session, [], query_text="西红柿炒鸡蛋", use_vector=True)
        assert results_fixed, "fixed 缺省模式仍应返回候选"
        assert all("_fusion_ranks" not in r for r in results_fixed), (
            "fixed 模式候选不应携带 _fusion_ranks 内部键"
        )
    finally:
        session.close()


def test_cli_build_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-11 CLI 增量回填幂等：连续两次 main(["build_embeddings"]) 行数不变（测试）。

    参数：
        monkeypatch：pytest 夹具（patch EMBEDDING_PROVIDER=hash，离线确定性）。

    异常：
        退出码非 0 或第二次调用后行数变化（幂等破坏）时断言失败。
    """
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")

    session = SessionLocal()

    def _count_verified_hash() -> int:
        """统计 verified + hash-v1 向量行数（内部函数）。

        返回值：
            int：行数。

        异常：
            查询异常向上抛出。
        """
        return int(
            session.execute(
                select(func.count()).select_from(RecipeEmbedding)
                .where(RecipeEmbedding.source == "verified")
                .where(RecipeEmbedding.embedding_model == "hash-v1")
            ).scalar_one()
        )

    try:
        assert main(["build_embeddings"]) == 0, "第一次增量回填退出码应为 0"
        count_1 = _count_verified_hash()
        assert count_1 > 0, "回填后 hash-v1 verified 行数应 > 0（种子库含 published 菜谱）"
        assert main(["build_embeddings"]) == 0, "第二次增量回填退出码应为 0"
        count_2 = _count_verified_hash()
        assert count_1 == count_2, f"增量幂等被破坏：第一次后 {count_1} 行，第二次后 {count_2} 行"
    finally:
        session.close()


def test_cli_rebuild_preserves_other_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-11 CLI --rebuild：仅重建目标空间，其他嵌入空间 verified 行不被触碰（测试）。

    流程：
        1. 任取一个 published 菜谱，插入 source='verified'、embedding_model='fake-v1' 行；
        2. main(["build_embeddings", "--rebuild"]) 退出码 0；
        3. hash-v1 verified 行数 >0（目标空间重建成功）且 fake-v1 行仍在（未触碰）。

    参数：
        monkeypatch：pytest 夹具（patch EMBEDDING_PROVIDER=hash，离线确定性）。

    异常：
        退出码非 0、目标空间未重建或外部空间行丢失时断言失败。
    """
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")

    session = SessionLocal()
    fake_row_id: int | None = None
    try:
        published_id = session.execute(
            select(Recipe.id).where(Recipe.status == "published").limit(1)
        ).scalar_one()
        assert published_id is not None, "种子库应存在 published 菜谱"
        fake_row = RecipeEmbedding(
            recipe_id=int(published_id), source="verified",
            embedding_json=[0.0] * 1024, embedding_model="fake-v1",
        )
        session.add(fake_row)
        session.commit()
        fake_row_id = int(fake_row.id)

        assert main(["build_embeddings", "--rebuild"]) == 0, "--rebuild 退出码应为 0"

        hash_count = session.execute(
            select(func.count()).select_from(RecipeEmbedding)
            .where(RecipeEmbedding.source == "verified")
            .where(RecipeEmbedding.embedding_model == "hash-v1")
        ).scalar_one()
        assert hash_count > 0, "--rebuild 后目标空间 hash-v1 verified 行应重建成功"
        assert session.execute(
            select(func.count()).select_from(RecipeEmbedding).where(RecipeEmbedding.id == fake_row_id)
        ).scalar_one() == 1, "其他嵌入空间（fake-v1）的 verified 行不得被 --rebuild 触碰"
    finally:
        # 自清理：删除测试插入的 fake-v1 行（兜底按 空间+source 清残留）
        session.rollback()
        if fake_row_id is not None:
            session.query(RecipeEmbedding).filter(
                RecipeEmbedding.id == fake_row_id
            ).delete(synchronize_session=False)
        session.query(RecipeEmbedding).filter(
            RecipeEmbedding.embedding_model == "fake-v1", RecipeEmbedding.source == "verified"
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
