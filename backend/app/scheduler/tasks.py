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

settings = get_settings()
scheduler = AsyncIOScheduler()


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


def _next_ai_time() -> datetime:
    """Calculate next AI process run time (fixed interval)."""
    return datetime.now() + timedelta(minutes=settings.AI_PROCESS_INTERVAL_MINUTES)


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

    async def _run():
        db = SessionLocal()
        try:
            manager = CollectorManager(db)
            articles = await manager.fetch_all()

            # Deduplicate by URL before saving (bulk check to avoid N+1)
            seen_urls = set()
            existing_urls = {url for url, in db.query(Article.url).all()}
            new_count = 0
            for raw in articles:
                if raw.url in seen_urls or raw.url in existing_urls:
                    continue
                seen_urls.add(raw.url)

                article = Article(
                    url=raw.url,
                    title=raw.title,
                    summary=raw.summary,
                    content=raw.content,
                    source_name=raw.source_name,
                    source_url=raw.source_url,
                    published_at=raw.published_at,
                    raw_hot_score=raw.raw_hot_score,
                    language=raw.language,
                )
                db.add(article)
                new_count += 1

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
    """

    async def _run():
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

            logger.info("AI process task complete")
        except Exception as e:
            logger.error(f"AI process task error: {e}")
            db.rollback()
        finally:
            db.close()

    asyncio.run(_run())

    # Reschedule next run with fixed interval
    try:
        scheduler.add_job(
            ai_process_task,
            trigger="date",
            run_date=_next_ai_time(),
            id="ai_process",
            replace_existing=True,
        )
    except Exception:
        logger.exception("Failed to reschedule AI process task")


def start_scheduler():
    """Start background scheduled tasks."""
    scheduler.start()

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
        run_date=_next_ai_time(),
        id="ai_process",
        replace_existing=True,
    )
    logger.info("Scheduler started: adaptive random intervals (day 30-60min, night 60-120min)")


def stop_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler stopped")
