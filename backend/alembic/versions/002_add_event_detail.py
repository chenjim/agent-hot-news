"""Add detail column to hot_events.

Revision ID: 002
Revises: 001
Create Date: 2026-06-11
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hot_events", sa.Column("detail", sa.Text))


def downgrade() -> None:
    op.drop_column("hot_events", "detail")
