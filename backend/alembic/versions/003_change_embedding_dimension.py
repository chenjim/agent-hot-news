"""Change embedding columns from 4096 to 1024 dimensions.

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Events are derived from embeddings and must be rebuilt with the new model.
    op.execute(sa.text("DELETE FROM event_articles"))
    op.execute(sa.text("DELETE FROM hot_events"))
    op.execute(sa.text("ALTER TABLE articles DROP COLUMN embedding"))
    op.execute(sa.text("ALTER TABLE articles ADD COLUMN embedding vector(1024)"))
    op.execute(sa.text("ALTER TABLE hot_events DROP COLUMN embedding_centroid"))
    op.execute(sa.text("ALTER TABLE hot_events ADD COLUMN embedding_centroid vector(1024)"))
    op.execute(sa.text("UPDATE articles SET is_processed = false"))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM event_articles"))
    op.execute(sa.text("DELETE FROM hot_events"))
    op.execute(sa.text("ALTER TABLE articles DROP COLUMN embedding"))
    op.execute(sa.text("ALTER TABLE articles ADD COLUMN embedding vector(4096)"))
    op.execute(sa.text("ALTER TABLE hot_events DROP COLUMN embedding_centroid"))
    op.execute(sa.text("ALTER TABLE hot_events ADD COLUMN embedding_centroid vector(4096)"))
    op.execute(sa.text("UPDATE articles SET is_processed = false"))
