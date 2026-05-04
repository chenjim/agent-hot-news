import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from loguru import logger

from app.database import get_db
from app.models.models import Article, HotEvent, Source, SourceStatus
from app.scheduler.tasks import fetch_task, ai_process_task

router = APIRouter()

# In-memory task execution logs (later can be moved to database)
_MAX_LOGS = 1000
_TASK_LOGS: deque[dict] = deque(maxlen=_MAX_LOGS)
_SERVER_START_TIME = datetime.now(timezone.utc)


def _append_log(task_name: str, status: str, message: str = ""):
    entry = {
        "id": str(len(_TASK_LOGS) + 1),
        "task": task_name,
        "status": "success" if status == "success" else "failed",
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TASK_LOGS.append(entry)


@router.get("/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    """System statistics dashboard."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    articles_today = (
        db.query(func.count(Article.id))
        .filter(Article.fetched_at >= today_start)
        .scalar()
        or 0
    )

    hot_events_today = (
        db.query(func.count(HotEvent.id))
        .filter(HotEvent.first_seen_at >= today_start)
        .scalar()
        or 0
    )

    total_articles = db.query(func.count(Article.id)).scalar() or 0
    total_events = db.query(func.count(HotEvent.id)).scalar() or 0

    sources = db.query(Source).all()
    source_health = []
    active_count = 0
    for src in sources:
        if src.status == SourceStatus.ACTIVE:
            active_count += 1
        source_health.append({
            "name": src.name,
            "type": src.type.value if src.type else None,
            "status": src.status.value if src.status else None,
            "last_fetched_at": src.last_fetched_at.isoformat() if src.last_fetched_at else None,
            "last_error": src.last_error,
        })

    uptime_seconds = int((datetime.now(timezone.utc) - _SERVER_START_TIME).total_seconds())

    return {
        "articles_today": articles_today,
        "events_today": hot_events_today,
        "total_articles": total_articles,
        "total_events": total_events,
        "active_sources": active_count,
        "total_sources": len(sources),
        "uptime_seconds": uptime_seconds,
        "sources_health": source_health,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/trigger-fetch")
async def trigger_fetch():
    """Manually trigger the article fetch task."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fetch_task)
        _append_log("fetch_task", "success", "Manually triggered fetch completed")
        return {"status": "ok", "message": "Fetch task triggered successfully"}
    except Exception as e:
        logger.error(f"Manual fetch trigger failed: {e}")
        _append_log("fetch_task", "error", str(e))
        raise HTTPException(status_code=500, detail="Fetch task failed")


@router.post("/trigger-ai")
async def trigger_ai():
    """Manually trigger the AI processing task."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ai_process_task)
        _append_log("ai_process_task", "success", "Manually triggered AI process completed")
        return {"status": "ok", "message": "AI process task triggered successfully"}
    except Exception as e:
        logger.error(f"Manual AI trigger failed: {e}")
        _append_log("ai_process_task", "error", str(e))
        raise HTTPException(status_code=500, detail="AI process task failed")


@router.get("/logs")
def get_logs(limit: int = 100) -> List[dict]:
    """Get recent task execution logs."""
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000
    return list(_TASK_LOGS)[-limit:]
