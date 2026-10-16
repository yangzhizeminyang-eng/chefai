"""user accounts (username/password + JWT auth)

Revision ID: e7a9b3c40d21
Revises: c5d8e2a94f17
Create Date: 2026-10-16

说明：
    用户账号体系迁移（web-stage1 登录/注册 + 多账号数据隔离）：
    1. user 表新增 username VARCHAR(50) NULL：注册账号登录名；
    2. user 表新增 password_hash VARCHAR(255) NULL：pbkdf2_sha256 哈希
       （与后台 admin_user 同口径），匿名用户两列为 NULL；
    3. 新增部分唯一索引 uq_user_username（仅对非空 username 生效），
       与既有 uq_user_openid 同模式；
    4. 注册流程将既有匿名用户的 username/password_hash 回填到原 user 行上，
       匿名期间产生的档案/库存/收藏等数据（均以 user_id 关联）自然延续，
       无需数据搬迁。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7a9b3c40d21'
down_revision: Union[str, Sequence[str], None] = 'c5d8e2a94f17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：user 表增加 username / password_hash 列与部分唯一索引（函数）。"""
    op.add_column('user', sa.Column('username', sa.String(length=50), nullable=True))
    op.add_column('user', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.create_index(
        'uq_user_username',
        'user',
        ['username'],
        unique=True,
        postgresql_where=sa.text('username IS NOT NULL'),
    )


def downgrade() -> None:
    """回滚：删除部分唯一索引与两列，恢复至 c5d8e2a94f17（函数）。"""
    op.drop_index('uq_user_username', table_name='user')
    op.drop_column('user', 'password_hash')
    op.drop_column('user', 'username')
