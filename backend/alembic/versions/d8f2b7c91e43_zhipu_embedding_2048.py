"""zhipu embedding 2048 column (halfvec/vector by extversion)

Revision ID: d8f2b7c91e43
Revises: e7a9b3c40d21
Create Date: 2026-10-16

说明：
    智谱 embedding-3 2048 维嵌入空间迁移（阶段 3 向量模型升级）：
    1. 背景与外部事实（已核实）：
       - 智谱 embedding-3 维度 256-2048 可自定义，本项目固定 2048 维；
       - pgvector 的 vector 类型可存 16000 维，但 ivfflat/hnsw 近似索引仅支持
         ≤2000 维 → vector(2048) 不能建近似索引；
       - pgvector ≥ 0.7.0 的 halfvec 类型（半精度）索引支持至 4000 维 →
         halfvec(2048) + hnsw halfvec_cosine_ops 可行。
    2. 分支策略（依据 SELECT extversion FROM pg_extension WHERE extname='vector'）：
       - 扩展不存在 → 记 WARNING 跳过建列与索引（与 b8d3f5a21c60「向量列仅扩展
         可用时创建」模式一致），迁移绝不失败，embedding_json 便携列不受影响；
         扩展缺失跳过建列后，安装扩展可运行 python -m app.vector_schema_reconcile 收敛（幂等）；
       - extversion ≥ 0.7.0 → embedding_zhipu halfvec(2048) 列 + hnsw
         halfvec_cosine_ops 索引 idx_emb_zhipu（近似检索）；
       - extversion < 0.7.0 → embedding_zhipu vector(2048) 列，无近似索引
         （顺序扫描；当前 ≈400 行规模下毫秒级，足够）。
    3. 数据隔离（GAP-4）：embedding_zhipu 仅承载 2048 维智谱空间向量（按
       embedding_model 列过滤），与 1024 维 embedding vector(1024) 列物理隔离，
       跨空间向量绝不通算余弦；该列不进 ORM，检索/写入层以 raw SQL 访问。
    4. 全部 DDL 以 IF NOT EXISTS / IF EXISTS 书写，重复执行幂等；
       经 op.get_bind().execute(sa.text(...)) 执行，alembic 事务性保证原子。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd8f2b7c91e43'
down_revision: Union[str, Sequence[str], None] = 'e7a9b3c40d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _vector_extversion() -> str | None:
    """读取 pgvector 扩展版本号（函数）。

    返回值：
        str | None：扩展已安装返回 extversion（如 '0.7.4'）；未安装返回 None。

    异常：
        数据库查询异常向上抛出（alembic 整体回滚）。
    """
    conn = op.get_bind()
    return conn.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()


def _version_tuple(version: str) -> tuple[int, ...]:
    """把扩展版本字符串解析为可比较的整数元组（函数）。

    说明：
        '0.7.4' → (0, 7, 4)；非数字后缀（如 '0.7.4rc1'）取前导数字，解析不出的段按 0。

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


def upgrade() -> None:
    """升级：按 pgvector 版本分支创建 embedding_zhipu 2048 维向量列与索引（函数）。

    执行顺序：
        探测扩展 → 不存在记 WARNING 直接返回；≥0.7.0 建 halfvec(2048) 列 + hnsw
        halfvec_cosine_ops 索引；<0.7.0 建 vector(2048) 列（无近似索引）。

    异常：
        数据库 DDL 失败时向上抛出（alembic 整体回滚，事务性 DDL 保证不留半成品）。
    """
    version = _vector_extversion()
    if not version:
        print(
            "[migration][WARNING] pgvector 扩展不可用（未安装 vector 包），"
            "跳过 embedding_zhipu 2048 维向量列与索引；"
            "向量便携存储 embedding_json(JSONB) 与表结构不受影响，"
            "智谱空间检索自动降级关键词路径。"
        )
        return
    conn = op.get_bind()
    if _version_tuple(version) >= (0, 7):
        # halfvec（半精度）索引支持至 4000 维：2048 维可建 hnsw 近似索引
        conn.execute(sa.text(
            "ALTER TABLE recipe_embedding "
            "ADD COLUMN IF NOT EXISTS embedding_zhipu halfvec(2048)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS idx_emb_zhipu "
            "ON recipe_embedding USING hnsw (embedding_zhipu halfvec_cosine_ops)"
        ))
    else:
        # vector(2048) 超出 ivfflat/hnsw 2000 维索引上限：不建近似索引，顺序扫描
        # （当前 ≈400 行规模足够；扩展升级 ≥0.7 后可手工重建为 halfvec + hnsw）
        conn.execute(sa.text(
            "ALTER TABLE recipe_embedding "
            "ADD COLUMN IF NOT EXISTS embedding_zhipu vector(2048)"
        ))


def downgrade() -> None:
    """回滚：删除智谱向量列与索引（函数）。

    说明：
        先删 idx_emb_zhipu 索引再删 embedding_zhipu 列；列/索引未建（扩展
        缺失环境）时 IF EXISTS 保证 no-op，不留残留。

    异常：
        数据库 DDL 失败时向上抛出。
    """
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_emb_zhipu"))
    conn.execute(sa.text("ALTER TABLE recipe_embedding DROP COLUMN IF EXISTS embedding_zhipu"))
