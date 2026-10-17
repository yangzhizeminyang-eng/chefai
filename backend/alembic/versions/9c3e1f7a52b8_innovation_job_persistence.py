"""innovation job persistence table

Revision ID: 9c3e1f7a52b8
Revises: d8f2b7c91e43
Create Date: 2026-10-17

说明：
    AI 创新异步任务持久化迁移（阶段 4 可靠性升级 / 改进方案 M-01 最小落地）：
    1. 新建 innovation_job 表：承载内存 job store 的写穿副本，进程重启后
       pending/running 任务可被识别并置为明确终态（failed），轮询方经
       DB fallback 拿到失败文案而非 404（端点契约与跨用户隔离口径不变）；
    2. status CHECK 五态（pending/running/succeeded/failed/blocked）与内存
       状态机一致；终态即冻结由应用层保证；
    3. idx_innovation_job_user 支持「按用户查询任务」与启动恢复扫描；
    4. downgrade 干净回滚：仅删本表，不影响其他对象。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9c3e1f7a52b8'
down_revision: Union[str, Sequence[str], None] = 'd8f2b7c91e43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 innovation_job 持久化表与索引（函数）。

    异常：
        数据库 DDL 失败时向上抛出（alembic 整体回滚，事务性 DDL 保证原子）。
    """
    op.create_table(
        'innovation_job',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('recipe', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('issues', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','blocked')",
            name='chk_job_status',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', name='uq_innovation_job_job_id'),
    )
    op.create_index('idx_innovation_job_user', 'innovation_job', ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    """回滚：删除 innovation_job 表（函数）。

    说明：
        先删索引再删表；本迁移只新建单表，回滚无残留。

    异常：
        数据库 DDL 失败时向上抛出。
    """
    op.drop_index('idx_innovation_job_user', table_name='innovation_job')
    op.drop_table('innovation_job')
