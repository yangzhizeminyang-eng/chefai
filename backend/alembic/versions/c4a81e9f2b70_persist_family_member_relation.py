"""Persist family member relationship.

Revision ID: c4a81e9f2b70
Revises: b2f6d9a4c7e1
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a81e9f2b70"
down_revision: Union[str, Sequence[str], None] = "b2f6d9a4c7e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "family_member",
        sa.Column("relation", sa.String(length=20), server_default="本人", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("family_member", "relation")
