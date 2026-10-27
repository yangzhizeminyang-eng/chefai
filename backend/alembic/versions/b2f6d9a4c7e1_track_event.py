"""track_event persistence table

Revision ID: b2f6d9a4c7e1
Revises: 9c3e1f7a52b8
Create Date: 2026-10-18

说明：
    用户行为埋点接收闭环迁移（additive，仅 CREATE TABLE + 索引）：
    1. 新建 track_event 表：承载 POST /v1/track/events 批量接收的埋点事件
       （匿名 ID 透传 / 白名单事件名 / 剥离敏感后的 JSONB 属性 / 客户端时间）；
    2. idx_track_event_anonymous / idx_track_event_name 支持管理员按匿名 ID
       与事件名的时间窗口审计查询；
    3. 超期数据按应用层 TRACK_RETENTION_DAYS（缺省 30 天）惰性清理，
       迁移层不建分区/定时任务；
    4. downgrade 干净回滚：仅删本表（先删索引），不影响其他对象。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2f6d9a4c7e1'
down_revision: Union[str, Sequence[str], None] = '9c3e1f7a52b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 track_event 表与两个查询索引（函数）。

    异常：
        数据库 DDL 失败时向上抛出（alembic 整体回滚，事务性 DDL 保证原子）。
    """
    op.create_table(
        'track_event',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('anonymous_id', sa.String(length=64), nullable=True),
        sa.Column('event_name', sa.String(length=64), nullable=False),
        sa.Column('properties', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('client_ts', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_track_event_anonymous', 'track_event', ['anonymous_id', 'created_at'], unique=False)
    op.create_index('idx_track_event_name', 'track_event', ['event_name', 'created_at'], unique=False)


def downgrade() -> None:
    """回滚：删除 track_event 表（函数）。

    说明：
        先删索引再删表；本迁移只新建单表，回滚无残留。

    异常：
        数据库 DDL 失败时向上抛出。
    """
    op.drop_index('idx_track_event_name', table_name='track_event')
    op.drop_index('idx_track_event_anonymous', table_name='track_event')
    op.drop_table('track_event')
