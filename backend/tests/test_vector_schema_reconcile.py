"""vector_schema_reconcile 幂等 schema 收敛工具单元测试（离线确定性，探测函数 monkeypatch）。

覆盖（问题四：pgvector 后装时数据库结构无法收敛）：
    - 扩展缺失：退出码 1，且不执行任何 DDL（绝不静默跳过）；
    - extversion >= 0.7：DDL 含 halfvec(2048) 列与 hnsw halfvec_cosine_ops 索引，退出码 0；
    - extversion < 0.7：DDL 含 vector(2048) 且无 hnsw 索引，退出码 0；
    - 列已存在（halfvec）：无 ALTER 语句，仅 CREATE INDEX IF NOT EXISTS 幂等，退出码 0；
    - recipe_embedding 表缺失：退出码 1 并提示先执行 alembic upgrade head。

monkeypatch 方式：
    reconcile 模块的探测与执行解耦——探测函数（_probe_table_exists /
    _probe_extversion / _probe_column_type / _probe_index_exists）按用例
    monkeypatch 为固定返回值；DDL 执行经伪引擎/伪连接记录 SQL 文本断言。

运行：
    .venv\\Scripts\\python.exe -m pytest tests/test_vector_schema_reconcile.py -q
"""

from __future__ import annotations

import types

import pytest

from app import vector_schema_reconcile as vsr


class _FakeConn:
    """伪数据库连接（辅助类）：仅记录 execute 收到的 SQL 文本。

    说明：
        探测查询全部被 monkeypatch 的 probe 函数接管（不触达 execute），
        execute 只会收到 reconcile 生成的 DDL，逐条记录供断言。

    异常：
        无。
    """

    def __init__(self) -> None:
        """构造函数：初始化语句记录列表（函数）。

        异常：
            无。
        """
        self.statements: list[str] = []

    def execute(self, sql: object, params: object = None) -> types.SimpleNamespace:
        """记录 SQL 并返回空结果占位（函数）。

        参数：
            sql：SQL 语句对象（text(...)，str() 后记录）。
            params：绑定参数（DDL 场景恒为 None，仅占位）。

        返回值：
            types.SimpleNamespace：空结果占位（scalar/first 恒返回 None）。

        异常：
            无。
        """
        self.statements.append(str(sql))
        return types.SimpleNamespace(scalar=lambda *a, **k: None, first=lambda *a, **k: None)

    def commit(self) -> None:
        """提交事务占位（函数）：伪连接无需真实提交。

        异常：
            无。
        """


class _FakeConnCtx:
    """伪连接上下文（辅助类）：支持 with 语法返回伪连接。

    说明：
        with 语句的 __enter__/__exit__ 在类型上查找（special method lookup），
        SimpleNamespace 实例属性设置 dunder 无效，故用真实类实现。

    异常：
        无。
    """

    def __init__(self, conn: _FakeConn) -> None:
        """构造函数：包裹伪连接（函数）。

        参数：
            conn：待返回的伪连接。

        异常：
            无。
        """
        self._conn = conn

    def __enter__(self) -> _FakeConn:
        """进入上下文：返回伪连接（函数）。

        返回值：
            _FakeConn：伪连接实例。

        异常：
            无。
        """
        return self._conn

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        """退出上下文：不吞异常（函数）。

        参数：
            exc_type：异常类型（无异常为 None）。
            exc：异常实例。
            tb：traceback 对象。

        返回值：
            bool：恒 False（异常继续向上传播）。

        异常：
            无。
        """
        return False


class _FakeEngine:
    """伪数据库引擎（辅助类）：connect() 返回上下文管理器包裹的伪连接。

    异常：
        无。
    """

    def __init__(self) -> None:
        """构造函数：持有单个伪连接（函数）。

        异常：
            无。
        """
        self.conn = _FakeConn()

    def connect(self) -> _FakeConnCtx:
        """返回支持 with 语法的连接上下文（函数）。

        返回值：
            _FakeConnCtx：__enter__ 返回伪连接、__exit__ 不吞异常。

        异常：
            无。
        """
        return _FakeConnCtx(self.conn)


def _patch_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    table_exists: bool = True,
    extversion: str | None = None,
    column_type: str | None = None,
    index_exists: bool = False,
) -> _FakeEngine:
    """按用例固定四个探测函数的返回值并注入伪引擎（辅助函数）。

    参数：
        monkeypatch：pytest.MonkeyPatch 实例。
        table_exists：recipe_embedding 表是否存在。
        extversion：pg_extension.extversion（None 表示扩展未安装）。
        column_type：embedding_zhipu 列类型（'halfvec' | 'vector' | None 缺失）。
        index_exists：idx_emb_zhipu 索引是否存在。

    返回值：
        _FakeEngine：已注入的伪引擎（测试据此断言 DDL 记录）。

    异常：
        无。
    """
    fake = _FakeEngine()
    monkeypatch.setattr(vsr, "_probe_table_exists", lambda conn: table_exists)
    monkeypatch.setattr(vsr, "_probe_extversion", lambda conn: extversion)
    monkeypatch.setattr(vsr, "_probe_column_type", lambda conn: column_type)
    monkeypatch.setattr(vsr, "_probe_index_exists", lambda conn: index_exists)
    return fake


def test_extension_missing_exits_1_without_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    """扩展缺失：退出码 1 且不执行任何 DDL（函数）。"""
    fake = _patch_probes(monkeypatch, table_exists=True, extversion=None)
    assert vsr.reconcile(fake) == 1
    assert fake.conn.statements == []


def test_ext_ge_07_builds_halfvec_and_hnsw(monkeypatch: pytest.MonkeyPatch) -> None:
    """extversion >= 0.7：DDL 含 halfvec(2048) 列与 hnsw halfvec_cosine_ops 索引（函数）。"""
    fake = _patch_probes(monkeypatch, extversion="0.7.4", column_type=None, index_exists=False)
    assert vsr.reconcile(fake) == 0
    joined = "\n".join(fake.conn.statements)
    assert "halfvec(2048)" in joined
    assert "ADD COLUMN IF NOT EXISTS embedding_zhipu" in joined
    assert "hnsw" in joined
    assert "halfvec_cosine_ops" in joined
    assert "CREATE INDEX IF NOT EXISTS idx_emb_zhipu" in joined


def test_ext_lt_07_builds_vector_without_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """extversion < 0.7：DDL 含 vector(2048) 且无 hnsw 索引（函数）。"""
    fake = _patch_probes(monkeypatch, extversion="0.6.2", column_type=None, index_exists=False)
    assert vsr.reconcile(fake) == 0
    joined = "\n".join(fake.conn.statements)
    assert "ADD COLUMN IF NOT EXISTS embedding_zhipu" in joined
    assert "vector(2048)" in joined
    assert "hnsw" not in joined
    assert "halfvec" not in joined


def test_column_exists_halfvec_no_alter_only_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """列已存在（halfvec）：无 ALTER，仅 CREATE INDEX IF NOT EXISTS 幂等（函数）。"""
    fake = _patch_probes(
        monkeypatch, extversion="0.7.4", column_type="halfvec", index_exists=False
    )
    assert vsr.reconcile(fake) == 0
    assert all("ALTER TABLE" not in stmt for stmt in fake.conn.statements)
    assert any(
        "CREATE INDEX IF NOT EXISTS idx_emb_zhipu" in stmt for stmt in fake.conn.statements
    )


def test_column_exists_halfvec_and_index_full_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """列与索引均已存在：零 DDL（完整幂等 no-op），退出码 0（函数）。"""
    fake = _patch_probes(
        monkeypatch, extversion="0.7.4", column_type="halfvec", index_exists=True
    )
    assert vsr.reconcile(fake) == 0
    assert fake.conn.statements == []


def test_table_missing_exits_1_with_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """recipe_embedding 表缺失：退出码 1 并提示先执行 alembic upgrade head（函数）。"""
    fake = _patch_probes(monkeypatch, table_exists=False)
    assert vsr.reconcile(fake) == 1
    assert fake.conn.statements == []
    out = capsys.readouterr().out
    assert "alembic upgrade head" in out
