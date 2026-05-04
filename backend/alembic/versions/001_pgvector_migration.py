"""Initial migration: create all tables with pgvector columns.

Revision ID: 001
Revises: None
Create Date: 2026-05-05
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from app.core.config import get_settings

EMBEDDING_DIM = get_settings().EMBEDDING_DIMENSION

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # sources
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("config", sa.JSON, default=dict),
        sa.Column("status", sa.String(16), default="active"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # articles
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.String(2048), unique=True, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(2048)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("raw_hot_score", sa.Float, default=0.0),
        sa.Column("language", sa.String(10), default="zh"),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("is_processed", sa.Boolean, default=False),
    )
    op.create_index("idx_articles_url", "articles", ["url"])
    op.create_index("idx_articles_source_name", "articles", ["source_name"])
    op.create_index("idx_articles_published_at", "articles", ["published_at"])

    # hot_events
    op.create_table(
        "hot_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("category", sa.String(64)),
        sa.Column("hot_score", sa.Float, default=0.0),
        sa.Column("trend", sa.String(16), default="stable"),
        sa.Column("sentiment", sa.String(16)),
        sa.Column("entities", sa.JSON),
        sa.Column("articles_count", sa.Integer, default=0),
        sa.Column("sources_count", sa.Integer, default=0),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
        sa.Column("cover_image", sa.String(2048)),
        sa.Column("embedding_centroid", Vector(EMBEDDING_DIM)),
    )
    op.create_index("idx_hot_events_category", "hot_events", ["category"])
    op.create_index("idx_hot_events_hot_score", "hot_events", ["hot_score"])

    # event_articles
    op.create_table(
        "event_articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer,
            sa.ForeignKey("hot_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relevance_score", sa.Float, default=1.0),
    )


def downgrade() -> None:
    op.drop_table("event_articles")
    op.drop_table("articles")
    op.drop_table("hot_events")
    op.drop_table("sources")
