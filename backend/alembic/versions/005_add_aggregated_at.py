"""Add hot_events.aggregated_at (发布聚合时间) + 存量回填。

Revision ID: 005
Revises: 004

回填口径：达标事件取「第 3 篇到达（按 fetched_at 正序第 3 条）的采集时间」
近似「从 2 篇到 3 篇的那一刻」。注意必须是正序第 3 —— 倒序第 3 对持续增长的
事件永远等于最近时间，会把老事件重新顶回首页。库里没有记录第 3 篇何时并入，
只能这样近似；未达标（不足 3 篇或只有 1 个来源）的事件留 NULL，等真正达标时再打点。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 达标口径：3 篇文章 + 至少 2 个来源（与 pipeline 里的 _stamp_aggregated 一致）
_BACKFILL = sa.text(
    """
    UPDATE hot_events e
    SET aggregated_at = t.third_fetched_at
    FROM (
        SELECT event_id, fetched_at AS third_fetched_at
        FROM (
            SELECT ea.event_id,
                   a.fetched_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY ea.event_id ORDER BY a.fetched_at ASC
                   ) AS rn
            FROM event_articles ea
            JOIN articles a ON a.id = ea.article_id
        ) ranked
        WHERE rn = 3
    ) t
    WHERE e.id = t.event_id
      AND e.aggregated_at IS NULL
      AND e.articles_count >= 3
      AND e.sources_count >= 2
    """
)


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE hot_events ADD COLUMN aggregated_at TIMESTAMPTZ"))
    op.execute(sa.text("CREATE INDEX ix_hot_events_aggregated_at ON hot_events (aggregated_at)"))
    op.execute(_BACKFILL)


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_hot_events_aggregated_at"))
    op.execute(sa.text("ALTER TABLE hot_events DROP COLUMN aggregated_at"))
