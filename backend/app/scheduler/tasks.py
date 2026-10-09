import asyncio
import random
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from loguru import logger

from app.database import SessionLocal
from app.collectors.manager import CollectorManager
from app.ai_pipeline.pipeline import AIPipeline
from app.models.models import Article, HotEvent
from app.core.config import get_settings

from app.scheduler.state import set_last_fetch_time, set_last_ai_time

settings = get_settings()
scheduler = AsyncIOScheduler()

AI_RETRY_SECONDS = 5  # brief delay before the next immediate pass when a backlog remains


def _next_fetch_time() -> datetime:
    """Calculate next fetch run time based on time-of-day.

    Daytime (08:00-20:00): random FETCH_INTERVAL_DAY_MIN~MAX minutes
    Nighttime (else):      random FETCH_INTERVAL_NIGHT_MIN~MAX minutes
    """
    now = datetime.now()
    hour = now.hour
    if 8 <= hour < 20:
        minutes = random.randint(
            settings.FETCH_INTERVAL_DAY_MIN, settings.FETCH_INTERVAL_DAY_MAX
        )
    else:
        minutes = random.randint(
            settings.FETCH_INTERVAL_NIGHT_MIN, settings.FETCH_INTERVAL_NIGHT_MAX
        )
    return now + timedelta(minutes=minutes)


def _next_ai_time(has_remaining: bool = False) -> datetime:
    """Calculate next AI process run time.

    When unprocessed articles remain, run again almost immediately to drain
    the backlog; otherwise keep the normal fixed interval.
    """
    if has_remaining:
        return datetime.now() + timedelta(seconds=AI_RETRY_SECONDS)
    return datetime.now() + timedelta(minutes=settings.AI_PROCESS_INTERVAL_MINUTES)


def _first_ai_time() -> datetime:
    """Run the first AI pass right after startup to avoid a long wait."""
    return datetime.now()


def _take_snapshot(db: Session) -> dict:
    """Take a snapshot of current hot events for comparison."""
    events = (
        db.query(HotEvent)
        .order_by(HotEvent.hot_score.desc())
        .limit(50)
        .all()
    )
    snapshot = {}
    for rank, event in enumerate(events, start=1):
        snapshot[event.id] = {
            "rank": rank,
            "title": event.title,
            "hot_score": event.hot_score,
        }
    return snapshot


async def _notify_sse_changes(before: dict, after: dict):
    """Detect and broadcast significant changes via SSE."""
    try:
        from app.api.v1.endpoints.sse import sse_manager
    except Exception:
        return

    messages = []

    # Detect new events
    for event_id, info in after.items():
        if event_id not in before:
            messages.append({
                "type": "new_event",
                "event_id": event_id,
                "title": info["title"],
                "rank": info["rank"],
                "hot_score": info["hot_score"],
            })

    # Detect rank changes > 3
    for event_id, info in after.items():
        if event_id in before:
            old_rank = before[event_id]["rank"]
            new_rank = info["rank"]
            if abs(old_rank - new_rank) > 3:
                messages.append({
                    "type": "rank_change",
                    "event_id": event_id,
                    "title": info["title"],
                    "old_rank": old_rank,
                    "new_rank": new_rank,
                    "hot_score": info["hot_score"],
                })

    for msg in messages:
        try:
            await sse_manager.broadcast(msg)
            logger.info(f"SSE broadcast: {msg['type']} - {msg.get('title', '')}")
        except Exception as e:
            logger.warning(f"SSE broadcast failed: {e}")


def fetch_task():
    """Scheduled task: fetch articles from all active sources.

    Runs in a background thread (via AsyncIOScheduler's default executor)
    so sync SQLAlchemy operations do not block the event loop.
    """
    from app.scheduler.state import set_last_fetch_time
    set_last_fetch_time()  # Mark fetch start time

    async def _run():
        db = SessionLocal()
        try:
            manager = CollectorManager(db)
            articles = await manager.fetch_all()

            # 原文不入库：带原文的条目先做 LLM 摘要，失败的本条跳过、下一轮重试。
            # 摘要前先做去重：已在库的条目（URL 或 来源+标题 命中）不再重复过 LLM，
            # 但保留在列表里，落库时照常刷新热度与采集时间。
            from app.ai_pipeline.article_summarizer import ArticleSummarizer

            existing = manager.load_existing(articles)
            articles = await ArticleSummarizer().process(
                articles, is_known=manager.known_predicate(*existing)
            )

            new_count = manager.save_articles(articles, existing=existing)
            db.commit()
            logger.info(f"Fetch task complete: {new_count} new articles saved")
        except Exception as e:
            logger.error(f"Fetch task error: {e}")
            db.rollback()
        finally:
            db.close()

    asyncio.run(_run())

    # Reschedule next run with adaptive interval
    try:
        scheduler.add_job(
            fetch_task,
            trigger="date",
            run_date=_next_fetch_time(),
            id="fetch_articles",
            replace_existing=True,
        )
    except Exception:
        logger.exception("Failed to reschedule fetch task")


def ai_process_task():
    """Scheduled task: run AI pipeline on unprocessed articles.

    Runs in a background thread (via AsyncIOScheduler's default executor)
    so sync SQLAlchemy operations do not block the event loop.
    Reschedules itself almost immediately when unprocessed articles remain.
    """
    from app.scheduler.state import set_last_ai_time
    set_last_ai_time()  # Mark AI process start time

    async def _run() -> bool:
        """Run one pipeline pass; return True if unprocessed articles remain."""
        db = SessionLocal()
        try:
            # Snapshot before processing
            before_snapshot = _take_snapshot(db)

            pipeline = AIPipeline(db)
            await pipeline.run(max_articles=settings.MAX_ARTICLES_PER_BATCH)

            # Snapshot after processing
            after_snapshot = _take_snapshot(db)

            # Notify SSE subscribers of changes
            await _notify_sse_changes(before_snapshot, after_snapshot)

            remaining = (
                db.query(Article)
                .filter(Article.is_processed.is_(False))
                .count()
            )
            logger.info(f"AI process task complete, {remaining} unprocessed articles remaining")
            return remaining > 0
        except Exception as e:
            logger.error(f"AI process task error: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    try:
        has_remaining = asyncio.run(_run())
    except Exception:
        has_remaining = False

    # Reschedule: drain the backlog quickly, otherwise use the fixed interval
    try:
        scheduler.add_job(
            ai_process_task,
            trigger="date",
            run_date=_next_ai_time(has_remaining),
            id="ai_process",
            replace_existing=True,
        )
    except Exception:
        logger.exception("Failed to reschedule AI process task")


def _cleanup_cutoff() -> datetime:
    """Cutoff for cleanup: delete data older than the retention window."""
    return datetime.now() - timedelta(days=settings.CLEANUP_RETENTION_DAYS)


def cleanup_task():
    """Scheduled task: delete articles and events older than the retention window."""
    cutoff = _cleanup_cutoff()

    async def _run():
        db = SessionLocal()
        try:
            # Delete old events first (cascade deletes event_articles)
            old_events = (
                db.query(HotEvent)
                .filter(HotEvent.last_updated_at < cutoff)
                .delete(synchronize_session=False)
            )

            # Delete old articles (cascade deletes remaining event_articles)
            old_articles = (
                db.query(Article)
                .filter(Article.fetched_at < cutoff)
                .delete(synchronize_session=False)
            )

            db.commit()
            logger.info(f"Cleanup complete: {old_events} events, {old_articles} articles deleted")
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")
            db.rollback()
        finally:
            db.close()

    asyncio.run(_run())


def start_scheduler():
    """Start background scheduled tasks."""
    scheduler.start()

    # Daily cleanup at 00:00
    scheduler.add_job(
        cleanup_task,
        trigger="cron",
        hour=0,
        minute=0,
        id="cleanup",
        replace_existing=True,
    )

    # Use date trigger so each task can dynamically reschedule itself after completion
    scheduler.add_job(
        fetch_task,
        trigger="date",
        run_date=_next_fetch_time(),
        id="fetch_articles",
        replace_existing=True,
    )
    scheduler.add_job(
        ai_process_task,
        trigger="date",
        run_date=_first_ai_time(),
        id="ai_process",
        replace_existing=True,
    )
    logger.info("Scheduler started: daily cleanup at 00:00, adaptive fetch intervals, AI runs immediately then on demand")


def stop_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler stopped")
