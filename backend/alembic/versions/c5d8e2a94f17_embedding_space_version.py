"""embedding space version tag

Revision ID: c5d8e2a94f17
Revises: b8d3f5a21c60
Create Date: 2026-10-12

说明：
    嵌入空间版本标识迁移（spec add-bailian-embedding-rag / 14 号设计文档 C2/GAP-4）：
    1. recipe_embedding 新增 embedding_model VARCHAR(64) NOT NULL DEFAULT 'hash-v1'：
       作为嵌入空间版本标识，防止 hash 伪向量与百炼语义向量混存于同一表
       导致余弦相似度跨空间比较错乱；server_default='hash-v1' 使存量行
       原子回填为 hash-v1，无需额外数据修复脚本；
    2. 新增 idx_emb_model 常规索引：检索/回填路径按当前提供方嵌入空间过滤；
    3. downgrade 干净回滚：先删索引再删列，不留任何残留。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c5d8e2a94f17'
down_revision: Union[str, Sequence[str], None] = 'b8d3f5a21c60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：recipe_embedding 增加嵌入空间版本标识列与索引（函数）。

    执行顺序：
        add_column embedding_model（server_default='hash-v1' 原子回填存量行）→
        create_index idx_emb_model。

    异常：
        数据库 DDL 失败时向上抛出（alembic 整体回滚，事务性 DDL 保证不留半成品）。
    """
    op.add_column('recipe_embedding', sa.Column('embedding_model', sa.String(length=64), server_default='hash-v1', nullable=False))
    op.create_index('idx_emb_model', 'recipe_embedding', ['embedding_model'], unique=False)


def downgrade() -> None:
    """回滚：删除嵌入空间版本标识列与索引（函数）。

    说明：
        先删 idx_emb_model 索引，再删 embedding_model 列，
        全量反向回滚至 b8d3f5a21c60，不留残留。

    异常：
        数据库 DDL 失败时向上抛出。
    """
    op.drop_index('idx_emb_model', table_name='recipe_embedding')
    op.drop_column('recipe_embedding', 'embedding_model')
