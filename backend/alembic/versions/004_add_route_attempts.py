"""Add articles.route_attempts (pending-pool aging counter, 方案 C).

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 已存在的行一律从 0 开始计数
    op.execute(sa.text("ALTER TABLE articles ADD COLUMN route_attempts INTEGER NOT NULL DEFAULT 0"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE articles DROP COLUMN route_attempts"))
