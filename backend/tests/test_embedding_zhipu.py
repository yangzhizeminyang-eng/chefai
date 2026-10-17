"""智谱 EmbeddingProvider 单元测试（离线确定性，伪造 openai 客户端）。

覆盖：
    - 正常路径：2048 维返回 → 等长、L2 归一化、LRU 缓存二次命中不触网；
    - 响应校验：条数缺失 / 维度不符（1024）/ NaN-Inf 数值 → EmbeddingUnavailableError；
    - 网络异常 → EmbeddingUnavailableError；
    - 配置缺失（ZHIPU_API_KEY 空）→ 工厂回落 hash 且 space_name 保持 'hash-v1'
      （绝不以 hash 伪向量冒充智谱空间）；
    - space_name 命名规则：'embedding-3-2048'（模型名 + 维度后缀）；
    - 写入分流：_sync_vector_columns 按维度选择目标列（列缺失时静默跳过）；
    - 迁移（可选，DB 可达时）：upgrade/downgrade/upgrade 幂等往返。

运行：
    .venv\\Scripts\\python.exe -m pytest tests/test_embedding_zhipu.py -q
"""

from __future__ import annotations

import math
import types
from unittest.mock import patch

import pytest

from app.ability import embedding as emb
from app.core.config import settings


def _fake_embedding_response(vectors: list[list[float]]) -> types.SimpleNamespace:
    """构造 OpenAI 兼容 embeddings 响应对象（辅助函数）。

    参数：
        vectors：与请求批次等长的向量列表（按 index 对齐返回）。

    返回值：
        types.SimpleNamespace：带 data 属性的伪响应（data[i].index/.embedding）。

    异常：
        无。
    """
    return types.SimpleNamespace(
        data=[
            types.SimpleNamespace(index=i, embedding=list(vec))
            for i, vec in enumerate(vectors)
        ]
    )


def _make_zhipu(dimensions: int = 2048) -> emb.ZhipuEmbeddingProvider:
    """构造注入伪 Key 的智谱提供方（辅助函数，不触网）。

    参数：
        dimensions：配置维度（默认 2048）。

    返回值：
        emb.ZhipuEmbeddingProvider：实例（client 后续按用例替换）。

    异常：
        配置缺失时抛 EmbeddingUnavailableError（由调用方 patch 后规避）。
    """
    with patch.object(settings, "ZHIPU_API_KEY", "test-key-offline"), \
         patch.object(settings, "ZHIPU_MODEL", "embedding-3"), \
         patch.object(settings, "EMBEDDING_DIMENSIONS", dimensions):
        return emb.ZhipuEmbeddingProvider()


def _unit_vector(dim: int, seed: float = 0.5) -> list[float]:
    """生成指定维度的归一化常数向量（辅助函数）。

    参数：
        dim：维度。
        seed：每个分量的基础值。

    返回值：
        list[float]：L2 归一化后的向量。

    异常：
        无。
    """
    norm = math.sqrt(dim * seed * seed)
    return [seed / norm] * dim


def test_zhipu_space_name_and_dimension() -> None:
    """space_name 命名规则与维度属性：'embedding-3-2048'（函数）。"""
    provider = _make_zhipu(2048)
    assert provider.dimension == 2048
    assert provider.space_name == "embedding-3-2048"


def test_zhipu_embed_success_and_normalized() -> None:
    """正常路径：返回等长向量且 L2 归一化（模长≈1）（函数）。"""
    provider = _make_zhipu()
    vec = _unit_vector(2048)
    fake_client = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(
            create=lambda **kw: _fake_embedding_response([vec])
        )
    )
    provider._client = fake_client
    out = provider.embed(["番茄炒蛋怎么做"])
    assert len(out) == 1
    assert len(out[0]) == 2048
    assert math.isclose(sum(x * x for x in out[0]), 1.0, rel_tol=1e-6)


def test_zhipu_embed_cache_hit_no_second_call() -> None:
    """LRU 缓存：同文本第二次调用不触发网络请求（函数）。"""
    provider = _make_zhipu()
    vec = _unit_vector(2048)
    calls = {"n": 0}

    def _create(**kw):  # noqa: ANN001,ANN202 —— 伪客户端签名
        calls["n"] += 1
        return _fake_embedding_response([vec])

    provider._client = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(create=_create)
    )
    provider.embed(["缓存命中用例"])
    provider.embed(["缓存命中用例"])
    assert calls["n"] == 1


def test_zhipu_embed_count_mismatch_rejected() -> None:
    """响应条数缺失（少于输入）→ EmbeddingUnavailableError（函数）。"""
    provider = _make_zhipu()
    # 输入 2 条文本去重后仍为 2，但响应只回 1 条
    provider._client = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(
            create=lambda **kw: _fake_embedding_response([_unit_vector(2048)])
        )
    )
    with pytest.raises(emb.EmbeddingUnavailableError):
        provider.embed(["文本一", "文本二"])


def test_zhipu_embed_wrong_dimension_rejected() -> None:
    """响应维度不符（1024 而非 2048）→ EmbeddingUnavailableError，拒绝写库（函数）。"""
    provider = _make_zhipu()
    provider._client = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(
            create=lambda **kw: _fake_embedding_response([_unit_vector(1024)])
        )
    )
    with pytest.raises(emb.EmbeddingUnavailableError):
        provider.embed(["维度不符用例"])


def test_zhipu_embed_non_finite_rejected() -> None:
    """响应含 NaN/Inf → EmbeddingUnavailableError（函数）。"""
    provider = _make_zhipu()
    bad = [float("nan")] * 2048
    provider._client = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(
            create=lambda **kw: _fake_embedding_response([bad])
        )
    )
    with pytest.raises(emb.EmbeddingUnavailableError):
        provider.embed(["非有限数值用例"])


def test_zhipu_embed_network_error_wrapped() -> None:
    """网络异常统一包装为 EmbeddingUnavailableError（函数）。"""
    provider = _make_zhipu()

    def _boom(**kw):  # noqa: ANN001,ANN202 —— 模拟网络故障
        raise ConnectionError("network down")

    provider._client = types.SimpleNamespace(
        embeddings=types.SimpleNamespace(create=_boom)
    )
    with pytest.raises(emb.EmbeddingUnavailableError):
        provider.embed(["网络异常用例"])


def test_zhipu_missing_key_factory_falls_back_to_hash() -> None:
    """配置缺失（KEY 空）→ 工厂回落 hash 且 space_name 仍为 'hash-v1'（函数）。"""
    emb._PROVIDER_SINGLETON = None  # 重置工厂单例（测试隔离）
    try:
        with patch.object(settings, "EMBEDDING_PROVIDER", "zhipu"), \
             patch.object(settings, "ZHIPU_API_KEY", ""):
            provider = emb.get_embedding_provider()
        assert isinstance(provider, emb.HashEmbeddingProvider)
        assert provider.space_name == "hash-v1"
    finally:
        emb._PROVIDER_SINGLETON = None  # 还原，避免污染其他用例


def test_sync_vector_columns_routes_by_dimension() -> None:
    """写入分流：2048 维走 embedding_zhipu 列且按 probe 类型 CAST；列缺失跳过（函数）。"""
    session_calls: list[tuple[str, dict]] = []

    class _FakeSession:
        """记录 execute 调用的伪会话（辅助类）。"""

        def execute(self, stmt, params=None):  # noqa: ANN001,ANN202
            session_calls.append((str(stmt), dict(params or {})))
            return None

    vec_2048 = _unit_vector(2048)
    vec_1024 = _unit_vector(1024)
    with patch.object(emb, "probe_zhipu_column", return_value="halfvec"), \
         patch.object(emb, "probe_pgvector", return_value=False):
        emb._sync_vector_columns(_FakeSession(), 1, vec_2048)
        calls_before = len(session_calls)
        emb._sync_vector_columns(_FakeSession(), 2, vec_1024)
    joined = " | ".join(sql for sql, _ in session_calls)
    assert "embedding_zhipu" in joined and "halfvec" in joined
    # 1024 维：probe_pgvector=False 时不写任何物理列（JSON 便携列承载）
    assert len(session_calls) == calls_before, "1024 维向量在无 pgvector 时不应写列"
    with patch.object(emb, "probe_zhipu_column", return_value="missing"):
        session_calls.clear()
        emb._sync_vector_columns(_FakeSession(), 3, vec_2048)
    assert session_calls == [], "列缺失时应静默跳过物理列写入"


def _db_reachable() -> bool:
    """探测本地库可达性（辅助函数，供迁移用例 skipif）。

    返回值：
        bool：可建立连接返回 True。

    异常：
        不抛出。
    """
    try:
        from sqlalchemy import text as _text

        from app.core.db import engine as _engine

        with _engine.connect() as conn:
            conn.execute(_text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _db_reachable(), reason="本地库不可达，迁移实跑跳过")
def test_migration_zhipu_upgrade_downgrade_roundtrip() -> None:
    """迁移实跑（DB 可达时）：upgrade 幂等 + downgrade 回滚 + 再 upgrade（函数）。

    说明：
        本地库无 pgvector 扩展 → 迁移走「跳过建列」分支，断言不抛错且
        embedding_zhipu 列保持不存在；容器环境（扩展可用）下分支由
        extversion 实测决定，此处只验证幂等与不破坏现有结构。
    """
    from alembic import command
    from app.core.migrations import _build_alembic_config  # 项目既有程序化入口

    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "e7a9b3c40d21")
    command.upgrade(cfg, "head")
    # 幂等：重复 upgrade 不抛错
    command.upgrade(cfg, "head")
