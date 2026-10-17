"""回填 CLI 与 ensure_embeddings 限量/force 安全测试（真实本地库 + 专用测试空间隔离）。

覆盖：
    - limit 边界（test_limit_boundaries）：0/1/2/超总量 → written 与 pending/remaining
      递减一致、实际写入行数与返回值一致；全量写完后重复执行不增行（全量幂等）；
    - force 失败安全（test_force_rollback_on_embed_failure）：远程 embed 抛错 →
      EmbeddingUnavailableError 向上抛出，测试空间旧行完整无损（行数/向量/空间
      标识均不变）——替代旧「先删后填」的预删风险；
    - force upsert 覆盖（test_force_upsert_overwrites）：事务内按 recipe_id 覆盖
      ——测试空间行数不变（覆盖非新增）、原行主键不变（非删除重建）、向量已更新；
    - CLI 自检分流（test_partial_self_check）：限量模式输出 planned/written/remaining
      与 partial_check（不输出全量 "self_check=PASS" 字样）；全量模式输出
      self_check=PASS（coverage=1.0）。

数据隔离：
    全部写入限定 source='verified' AND embedding_model='test-backfill-space'；
    fixture teardown 统一删除该空间全部行，绝不触碰 hash-v1/zhipu 等真实空间；
    provider 用可编程 stub（纯 Python 生成 2048 维归一化向量，可编程失败），
    绝不触网；limit 边界用库内真实 published 菜谱前 3 篇 + 占位行收敛 pending
    规模为 3，不新建菜谱数据。

运行：
    .venv\\Scripts\\python.exe -m pytest tests/test_embedding_backfill.py -q
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

import app.embedding_backfill as backfill_mod
from app.ability import embedding as emb
from app.ability.embedding import ensure_embeddings
from app.core.db import SessionLocal
from app.models import Recipe, RecipeEmbedding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

# 测试专用嵌入空间标识（全部写入携带 embedding_model=该值；fixture teardown 统一删除，
# 绝不触碰 hash-v1 / qwen3.7-text-embedding / embedding-3-2048 等真实空间）
TEST_SPACE = "test-backfill-space"

# stub 向量维度（2048，与智谱空间同维度：验证非 1024 维写入分流，绝不触碰 embedding vector(1024) 列）
_STUB_DIM = 2048

# limit 边界测试的 pending 规模（库内真实 published 菜谱前 N 篇）
_PENDING_N = 3


class _StubProvider(emb.EmbeddingProvider):
    """可控桩嵌入提供方（测试辅助类）：纯 Python 生成归一化向量，行为可编程。

    说明：
        dimension=2048；每次 embed 调用产出新一代向量（由 _calls 计数与
        salt_offset 决定，确定性可复现），供 force 覆盖测试断言「向量已更新」；
        fail_immediately=True 时 embed 一调用即抛 EmbeddingUnavailableError，
        供 force 回滚安全测试验证「旧行无损」。
    """

    dimension = _STUB_DIM
    space_name = TEST_SPACE

    def __init__(self, salt_offset: float = 0.0, fail_immediately: bool = False) -> None:
        """构造函数（函数）。

        参数：
            salt_offset：向量族偏移（不同实例取不同值时向量族必不同）。
            fail_immediately：embed 一调用即抛统一不可用异常。

        返回值：
            None。

        异常：
            无。
        """
        self._salt_offset = salt_offset
        self._fail = fail_immediately
        self._calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量桩嵌入（函数）。

        参数：
            texts：待嵌入文本列表。

        返回值：
            list[list[float]]：与 texts 等长的 2048 维归一化向量列表。

        异常：
            EmbeddingUnavailableError：fail_immediately=True 时一调用即抛。
        """
        self._calls += 1
        if self._fail:
            raise emb.EmbeddingUnavailableError("stub embed failure（程序化失败）")
        return [
            _make_vector(_STUB_DIM, salt=self._salt_offset + 10.0 * self._calls + 0.001 * i)
            for i in range(len(texts))
        ]


def _make_vector(dim: int, salt: float) -> list[float]:
    """生成确定性归一化向量（辅助函数，salt 决定向量族）。

    参数：
        dim：向量维度。
        salt：族盐值（不同 salt → 不同向量，且 L2 范数恒为 1）。

    返回值：
        list[float]：L2 归一化后的向量。

    异常：
        无。
    """
    vec = [0.01 + salt * ((i % 7) + 1) / 7.0 for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]


def _pick_published_ids(session: Session, n: int = _PENDING_N) -> list[int]:
    """取库内前 n 篇 published 菜谱 ID（辅助函数，不新建菜谱数据）。

    参数：
        session：数据库会话。
        n：取用篇数。

    返回值：
        list[int]：菜谱 ID 列表（按 id 升序，确定性）。

    异常：
        库内 published 不足 n 篇时断言失败。
    """
    rows = session.execute(
        select(Recipe.id).where(Recipe.status == "published").order_by(Recipe.id).limit(n)
    ).all()
    ids = [int(rid) for (rid,) in rows]
    assert len(ids) == n, f"库内 published 菜谱不足 {n} 篇，limit 边界测试前置条件不满足"
    return ids


def _preset_placeholder_rows(session: Session, keep_ids: set[int]) -> int:
    """为除 keep_ids 外全部 published 菜谱在测试空间插占位向量行（辅助函数）。

    说明：
        占位后测试空间 pending 恰为 len(keep_ids)，limit 边界断言即可收敛在
        3 条小规模数据上；占位行同样写合法 2048 维向量，避免 partial_check
        抽样把占位行误判为维度不符。

    参数：
        session：数据库会话（写入即 commit）。
        keep_ids：保持 pending 的菜谱 ID 集合。

    返回值：
        int：插入的占位行数。

    异常：
        数据库异常向上抛出。
    """
    published_ids = [
        int(rid)
        for (rid,) in session.execute(select(Recipe.id).where(Recipe.status == "published")).all()
    ]
    vec = _make_vector(_STUB_DIM, salt=999.0)
    rows = [
        RecipeEmbedding(
            recipe_id=rid,
            source="verified",
            embedding_json=list(vec),
            embedding_model=TEST_SPACE,
        )
        for rid in published_ids
        if rid not in keep_ids
    ]
    session.add_all(rows)
    session.commit()
    return len(rows)


def _space_rows(session: Session) -> list[RecipeEmbedding]:
    """查询测试空间全部 verified 向量行（辅助函数）。

    参数：
        session：数据库会话。

    返回值：
        list[RecipeEmbedding]：该空间全部行。

    异常：
        数据库异常向上抛出。
    """
    return list(
        session.execute(
            select(RecipeEmbedding)
            .where(RecipeEmbedding.source == "verified")
            .where(RecipeEmbedding.embedding_model == TEST_SPACE)
        ).scalars().all()
    )


def _reset_space(session: Session, keep_ids: set[int]) -> None:
    """清空测试空间并重新按 keep_ids 预置占位行（辅助，limit 子场景间复位状态）。

    参数：
        session：数据库会话。
        keep_ids：保持 pending 的菜谱 ID 集合。

    返回值：
        None。

    异常：
        数据库异常向上抛出。
    """
    session.rollback()
    session.query(RecipeEmbedding).filter(
        RecipeEmbedding.source == "verified",
        RecipeEmbedding.embedding_model == TEST_SPACE,
    ).delete(synchronize_session=False)
    session.commit()
    _preset_placeholder_rows(session, keep_ids)


@pytest.fixture()
def backfill_session() -> Iterator[Session]:
    """测试空间隔离会话 fixture（fixture）。

    说明：
        连接真实本地库；teardown 先 rollback 丢弃残余事务，再统一删除
        source='verified' AND embedding_model='test-backfill-space' 的全部行
        （真实空间 hash-v1/zhipu 一律不触碰），最后 commit 并关闭会话。

    返回值：
        Iterator[Session]：SQLAlchemy 会话。

    异常：
        数据库不可达属环境前置条件不满足，测试直接失败。
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.query(RecipeEmbedding).filter(
            RecipeEmbedding.source == "verified",
            RecipeEmbedding.embedding_model == TEST_SPACE,
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_limit_boundaries(backfill_session) -> None:
    """limit 边界：0/1/2/超总量 → written 与 pending/remaining 一致（测试）。

    说明：
        每个子场景前复位测试空间（占位后 pending=3）；断言矩阵：
        limit=0 → written=0、planned=0；limit=1 → written=1、remaining=2；
        limit=2 → written=2；limit=10 → written=3=全部、remaining=0；
        末尾验证全量幂等：无 --limit/--force 重复执行不增行。

    参数：
        backfill_session：测试空间隔离会话 fixture。

    异常：
        断言失败即测试失败。
    """
    session = backfill_session
    keep = set(_pick_published_ids(session))
    stub = _StubProvider()

    # 场景 A：limit=0 → 不写任何行，pending 不变（planned=0）
    _reset_space(session, keep)
    assert backfill_mod._count_pending(session, TEST_SPACE) == _PENDING_N
    written_0 = ensure_embeddings(session, stub, space_name=TEST_SPACE, limit=0)
    assert written_0 == 0, "limit=0 应写入 0 行"
    assert backfill_mod._count_pending(session, TEST_SPACE) == _PENDING_N, "limit=0 后 pending 不应变"

    # 场景 B：limit=1 → 写 1 行，remaining=2
    _reset_space(session, keep)
    written_1 = ensure_embeddings(session, stub, space_name=TEST_SPACE, limit=1)
    assert written_1 == 1, "limit=1 应恰好写入 1 行"
    assert backfill_mod._count_pending(session, TEST_SPACE) == _PENDING_N - 1, "limit=1 后 remaining 应为 2"

    # 场景 C：limit=2 → 写 2 行，remaining=1
    _reset_space(session, keep)
    written_2 = ensure_embeddings(session, stub, space_name=TEST_SPACE, limit=2)
    assert written_2 == 2, "limit=2 应恰好写入 2 行"
    assert backfill_mod._count_pending(session, TEST_SPACE) == _PENDING_N - 2, "limit=2 后 remaining 应为 1"

    # 场景 D：limit 超过 pending → 写全部 3 行，remaining=0；且实际写入 recipe_id 与返回值一致
    _reset_space(session, keep)
    written_all = ensure_embeddings(session, stub, space_name=TEST_SPACE, limit=10)
    assert written_all == _PENDING_N, "limit 超过 pending 时应写入全部待处理记录"
    assert backfill_mod._count_pending(session, TEST_SPACE) == 0, "limit=10 后 remaining 应为 0"
    covered = {int(r.recipe_id) for r in _space_rows(session) if int(r.recipe_id) in keep}
    assert covered == keep, f"实际写入行应覆盖全部 pending 菜谱，实际 {covered}"

    # 全量幂等（约束 3）：无 --limit/--force 重复执行不增行
    total = len(_space_rows(session))
    assert ensure_embeddings(session, _StubProvider(salt_offset=50.0), space_name=TEST_SPACE) == 0
    assert len(_space_rows(session)) == total, "全量幂等被破坏：重复执行增加了行"


def test_force_rollback_on_embed_failure(backfill_session) -> None:
    """🔴 force 失败安全：embed 抛错 → 异常上抛、旧行无损（测试）。

    流程：
        1. 正常 stub 在测试空间写入 3 行（记录行数与各行向量）；
        2. 换失败 stub（embed 即抛 EmbeddingUnavailableError）+ force=True；
        3. 断言异常向上抛出，且测试空间行数仍为 3、各行 embedding_json 与
           embedding_model 均未变（事务回滚保证旧行无损，绝不出现空空间）。

    参数：
        backfill_session：测试空间隔离会话 fixture。

    异常：
        断言失败即测试失败。
    """
    session = backfill_session
    written = ensure_embeddings(session, _StubProvider(), space_name=TEST_SPACE, limit=_PENDING_N)
    assert written == _PENDING_N
    rows_before = {
        int(r.recipe_id): (int(r.id), list(r.embedding_json), r.embedding_model)
        for r in _space_rows(session)
    }
    assert len(rows_before) == _PENDING_N

    failing = _StubProvider(fail_immediately=True)
    with pytest.raises(emb.EmbeddingUnavailableError):
        ensure_embeddings(session, failing, space_name=TEST_SPACE, force=True)

    rows_after = {
        int(r.recipe_id): (int(r.id), list(r.embedding_json), r.embedding_model)
        for r in _space_rows(session)
    }
    assert rows_after == rows_before, "force 失败后旧行必须完整无损（行数/向量/空间标识均不变）"
    assert all(model == TEST_SPACE for _, _, model in rows_after.values()), "embedding_model 不得被改动"


def test_force_upsert_overwrites(backfill_session) -> None:
    """force upsert 覆盖：事务内按 recipe_id 覆盖，行数不变、向量更新（测试）。

    流程：
        1. 预置占位行（保留 3 篇 pending）→ 正常 stub 全量回填写 3 行；
        2. 换不同向量族的 stub + force=True → 全部 published 目标事务内 upsert；
        3. 断言测试空间总行数不变（覆盖非新增）、原 3 行主键不变（非删除重建）、
           向量已更新为新向量族。

    参数：
        backfill_session：测试空间隔离会话 fixture。

    异常：
        断言失败即测试失败。
    """
    session = backfill_session
    keep = set(_pick_published_ids(session))
    _preset_placeholder_rows(session, keep)
    assert ensure_embeddings(session, _StubProvider(), space_name=TEST_SPACE) == _PENDING_N

    total_before = len(_space_rows(session))
    keep_before = {
        int(r.recipe_id): (int(r.id), list(r.embedding_json))
        for r in _space_rows(session)
        if int(r.recipe_id) in keep
    }
    assert len(keep_before) == _PENDING_N

    written = ensure_embeddings(session, _StubProvider(salt_offset=1000.0), space_name=TEST_SPACE, force=True)
    assert written == total_before, "force 模式返回值应为本次处理的目标数（全部 published）"
    assert len(_space_rows(session)) == total_before, "force 覆盖不得增行（覆盖非新增）"

    keep_after = {
        int(r.recipe_id): (int(r.id), list(r.embedding_json))
        for r in _space_rows(session)
        if int(r.recipe_id) in keep
    }
    for rid, (old_id, old_vec) in keep_before.items():
        new_id, new_vec = keep_after[rid]
        assert new_id == old_id, "force 覆盖应更新原行（主键不变），而非删除重建"
        assert new_vec != old_vec, "force 覆盖后向量应已更新"


def test_partial_self_check(
    backfill_session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI 自检分流：限量 partial_check / 全量 self_check=PASS（测试）。

    流程：
        1. 预置占位行（pending=3）→ monkeypatch 工厂返回 stub（离线、可编程）；
        2. main(["--limit", "1"]) → 退出码 0，输出含 planned=1/written=1/remaining=2
           与 partial_check=ok，不含全量 "self_check=PASS" 字样；
        3. 复位后 main([]) 全量跑 → 退出码 0，输出含 planned=3/written=3/remaining=0
           与 self_check=PASS。

    参数：
        backfill_session：测试空间隔离会话 fixture。
        monkeypatch：pytest 夹具（替换 CLI 工厂注入 stub）。
        capsys：pytest 夹具（捕获 stdout）。

    异常：
        断言失败即测试失败。
    """
    session = backfill_session
    keep = set(_pick_published_ids(session))
    _preset_placeholder_rows(session, keep)
    monkeypatch.setattr(backfill_mod, "get_embedding_provider", lambda: _StubProvider())

    # 限量模式：真实写入 1 行 + partial_check（不得出现全量 PASS 字样）
    rc_limited = backfill_mod.main(["--limit", "1"])
    out_limited = capsys.readouterr().out
    assert rc_limited == 0, f"限量回填应退出 0，实际 {rc_limited}\n{out_limited}"
    assert "planned=1" in out_limited, f"输出应含 planned=1\n{out_limited}"
    assert "written=1" in out_limited, f"输出应含 written=1\n{out_limited}"
    assert "remaining=2" in out_limited, f"输出应含 remaining=2\n{out_limited}"
    assert "partial_check=ok" in out_limited, f"限量模式应输出 partial_check=ok\n{out_limited}"
    assert "self_check=PASS" not in out_limited, "限量模式不得输出全量 self_check=PASS 字样"

    # 全量模式：coverage=1.0 → self_check=PASS
    _reset_space(session, keep)
    rc_full = backfill_mod.main([])
    out_full = capsys.readouterr().out
    assert rc_full == 0, f"全量回填应退出 0，实际 {rc_full}\n{out_full}"
    assert "planned=3" in out_full, f"输出应含 planned=3\n{out_full}"
    assert "written=3" in out_full, f"输出应含 written=3\n{out_full}"
    assert "remaining=0" in out_full, f"输出应含 remaining=0\n{out_full}"
    assert "self_check=PASS" in out_full, f"全量模式应输出 self_check=PASS\n{out_full}"
