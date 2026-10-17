"""pgvector 后装场景幂等 schema 收敛工具（python -m app.vector_schema_reconcile）。

职责（问题四：pgvector 后装时数据库结构无法收敛）：
    迁移 d8f2b7c91e43 在 pgvector 扩展缺失时记 WARNING 跳过建列，但 Alembic 仍把该
    revision 记为已完成——之后在同一库安装扩展，alembic upgrade head 不会重放迁移，
    embedding_zhipu 列与 idx_emb_zhipu 索引永久缺失。本工具幂等收敛该差异：
        1. 前置探测：recipe_embedding 表不存在（空库未跑迁移）→ 提示先
           alembic upgrade head，退出码 1；pgvector 扩展未安装 → 提示安装并
           指向 README「pgvector 后装场景收敛」，退出码 1（绝不静默跳过）；
        2. extversion >= 0.7：按需 ALTER TABLE ... ADD COLUMN IF NOT EXISTS
           embedding_zhipu halfvec(2048) + CREATE INDEX IF NOT EXISTS idx_emb_zhipu
           （USING hnsw halfvec_cosine_ops）；
           extversion < 0.7：按需 ADD COLUMN embedding_zhipu vector(2048)（无近似索引）；
        3. 重复执行/部分结构已存在（列在索引不在、索引在列不在）均安全
           （全部 DDL 带 IF NOT EXISTS，列已存在不再 ALTER）；
        4. 结束输出状态摘要（extversion / 列类型 / 索引存在性）；
        5. 不改写任何已发布迁移的升级语义，仅补齐缺失结构。

用法（Windows PowerShell，backend/ 目录下）：
    .venv\\Scripts\\python.exe -m app.vector_schema_reconcile

退出码：
    0 成功（含幂等 no-op）；1 前置条件不满足（表缺失/扩展缺失）；
    2 数据库不可达或 DDL 执行失败。

异常：
    连接/执行异常在 main() 统一捕获，进程以非 0 退出码结束（不阻断应用，
    既有「无 pgvector → JSON 点积降级」行为不变）。
"""

from __future__ import annotations

import sys

from sqlalchemy import Connection, text

from app.core.db import engine

# DDL 常量（与迁移 d8f2b7c91e43 分支语义一致；全部 IF NOT EXISTS 幂等）
_DDL_ADD_HALFVEC = (
    "ALTER TABLE recipe_embedding ADD COLUMN IF NOT EXISTS embedding_zhipu halfvec(2048)"
)
_DDL_ADD_VECTOR = (
    "ALTER TABLE recipe_embedding ADD COLUMN IF NOT EXISTS embedding_zhipu vector(2048)"
)
_DDL_CREATE_HNSW_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_emb_zhipu "
    "ON recipe_embedding USING hnsw (embedding_zhipu halfvec_cosine_ops)"
)


def _version_tuple(version: str) -> tuple[int, ...]:
    """把扩展版本字符串解析为可比较的整数元组（函数）。

    说明：
        '0.7.4' → (0, 7, 4)；非数字后缀（如 '0.7.4rc1'）取前导数字，解析不出
        的段按 0（与迁移 d8f2b7c91e43 同规则；独立实现避免 import 迁移文件）。

    参数：
        version：pg_extension.extversion 字符串。

    返回值：
        tuple[int, ...]：至少三段的整数元组（缺失补 0）。

    异常：
        无。
    """
    parts: list[int] = []
    for piece in version.strip().split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _probe_table_exists(conn: Connection) -> bool:
    """探测 recipe_embedding 表是否存在（函数）。

    参数：
        conn：SQLAlchemy Connection。

    返回值：
        bool：information_schema.tables 中存在该表返回 True，否则 False。

    异常：
        数据库异常向上抛出（由 main() 统一捕获）。
    """
    row = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'recipe_embedding'")
    ).first()
    return row is not None


def _probe_extversion(conn: Connection) -> str | None:
    """探测 pgvector 扩展版本（函数）。

    参数：
        conn：SQLAlchemy Connection。

    返回值：
        str | None：扩展已安装返回 extversion（如 '0.7.4'）；未安装返回 None。

    异常：
        数据库异常向上抛出（由 main() 统一捕获）。
    """
    return conn.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()


def _probe_column_type(conn: Connection) -> str | None:
    """探测 embedding_zhipu 列的实际类型（函数）。

    参数：
        conn：SQLAlchemy Connection。

    返回值：
        str | None：'halfvec' | 'vector'（information_schema.columns 的 udt_name）；
        列不存在或类型无法识别返回 None。

    异常：
        数据库异常向上抛出（由 main() 统一捕获）。
    """
    udt = conn.execute(
        text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_name = 'recipe_embedding' AND column_name = 'embedding_zhipu'"
        )
    ).scalar()
    return udt if udt in ("halfvec", "vector") else None


def _probe_index_exists(conn: Connection) -> bool:
    """探测 idx_emb_zhipu 索引是否存在（函数）。

    参数：
        conn：SQLAlchemy Connection。

    返回值：
        bool：pg_indexes 中存在该索引返回 True，否则 False。

    异常：
        数据库异常向上抛出（由 main() 统一捕获）。
    """
    row = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_emb_zhipu'")
    ).first()
    return row is not None


def reconcile(db_engine=engine) -> int:
    """幂等收敛 recipe_embedding 的智谱向量结构（函数，探测与执行解耦供测试替换）。

    执行顺序：
        表存在性探测 → 扩展版本探测 → 按版本分支补建列/索引（全部 IF NOT EXISTS）
        → 终态复探输出摘要。列已存在（无论类型）不再 ALTER；列类型为 vector
        （旧版扩展所建）时跳过 hnsw halfvec_cosine_ops 索引（类型不匹配必报错）。

    参数：
        db_engine：SQLAlchemy Engine（默认 app.core.db.engine；测试注入伪引擎）。

    返回值：
        int：0 成功（含幂等 no-op）；1 表缺失/扩展缺失（带明确提示，不静默）。

    异常：
        数据库连接/DDL 异常向上抛出（由 main() 统一捕获退出）。
    """
    executed: list[str] = []
    with db_engine.connect() as conn:
        if not _probe_table_exists(conn):
            print(
                "[reconcile][ERROR] recipe_embedding 表不存在（空库尚未执行迁移）。"
                "请先运行 alembic upgrade head 建表，再执行本工具收敛向量结构。"
            )
            return 1
        extversion = _probe_extversion(conn)
        if not extversion:
            print(
                "[reconcile][ERROR] pgvector 扩展未安装"
                "（SELECT extversion FROM pg_extension WHERE extname='vector' 为空）。"
            )
            print(
                "  处理：安装含 pgvector 的 PostgreSQL（如 pgvector/pgvector:pg16 镜像）"
                "并执行 CREATE EXTENSION IF NOT EXISTS vector;"
            )
            print(
                "  详见 backend/README.md「pgvector 后装场景收敛」一节；"
                "安装扩展后重新运行本工具即可（幂等，可重复执行）。"
            )
            return 1
        column_type = _probe_column_type(conn)
        index_exists = _probe_index_exists(conn)
        if _version_tuple(extversion) >= (0, 7):
            if column_type is None:
                conn.execute(text(_DDL_ADD_HALFVEC))
                executed.append(_DDL_ADD_HALFVEC)
            if column_type != "vector" and not index_exists:
                # 列类型为 halfvec（或缺列刚补建）才可建 hnsw halfvec_cosine_ops 索引
                conn.execute(text(_DDL_CREATE_HNSW_INDEX))
                executed.append(_DDL_CREATE_HNSW_INDEX)
        else:
            if column_type is None:
                # vector(2048) 超出 ivfflat/hnsw 2000 维上限：不建近似索引，顺序扫描
                conn.execute(text(_DDL_ADD_VECTOR))
                executed.append(_DDL_ADD_VECTOR)
        # DDL 后复探真实终态（供状态摘要；幂等重跑时与前置探测一致）
        column_type = _probe_column_type(conn)
        index_exists = _probe_index_exists(conn)
        conn.commit()
    print(f"[reconcile] extversion={extversion}")
    print(f"[reconcile] embedding_zhipu 列类型={column_type or '缺失'}")
    print(f"[reconcile] idx_emb_zhipu 索引存在={index_exists}")
    if executed:
        for ddl in executed:
            print(f"[reconcile] 已执行 DDL: {ddl}")
    else:
        print("[reconcile] 结构已就绪，无需变更（幂等 no-op）。")
    return 0


def main() -> int:
    """CLI 主入口（函数）。

    返回值：
        int：0 成功（含幂等 no-op）；1 前置条件不满足；2 数据库不可达或执行失败。

    异常：
        不向上抛出（连接/执行异常统一捕获后按退出码 2 结束，输出错误摘要）。
    """
    try:
        return reconcile(engine)
    except Exception as exc:  # noqa: BLE001 —— CLI 边界统一捕获，按退出码退出
        print(f"[reconcile][ERROR] 数据库不可达或执行失败: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
