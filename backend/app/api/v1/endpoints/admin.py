import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import require_read, require_write
from app.core.system_meta import get_first_started_at, init_first_started_at
from sqlalchemy import func
from sqlalchemy.orm import Session
from loguru import logger

from app.database import get_db
from app.models.models import Article, HotEvent, Source, SourceStatus
from app.scheduler.tasks import fetch_task, ai_process_task
from app.scheduler.state import (
    get_last_fetch_time, set_last_fetch_time,
    get_last_ai_time, set_last_ai_time,
    FETCH_COOLDOWN_SECONDS, AI_COOLDOWN_SECONDS,
)
from app.utils.timezone import get_tz

router = APIRouter()

# In-Memory task execution logs (later can be moved to database)
_MAX_LOGS = 1000
_TASK_LOGS: deque[dict] = deque(maxlen=_MAX_LOGS)
_log_ids = count(1)
_SERVER_START_TIME = datetime.now(timezone.utc)


def _append_log(task_name: str, status: str, message: str = ""):
    entry = {
        "id": str(next(_log_ids)),
        "task": task_name,
        "status": "success" if status == "success" else "failed",
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TASK_LOGS.append(entry)


@router.get("/stats", dependencies=[Depends(require_read)])
def get_admin_stats(db: Session = Depends(get_db), tz: str = Query("Asia/Shanghai")):
    """System statistics dashboard."""
    today_start = datetime.now(get_tz(tz)).replace(hour=0, minute=0, second=0, microsecond=0)

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

        # Count articles fetched from this source today
        fetched_today = (
            db.query(func.count(Article.id))
            .filter(Article.source_name == src.name)
            .filter(Article.fetched_at >= today_start)
            .scalar()
            or 0
        )

        source_health.append({
            "id": src.id,
            "name": src.name,
            "type": src.type.value if src.type else None,
            "status": src.status.value if src.status else None,
            "last_fetched_at": src.last_fetched_at.isoformat() if src.last_fetched_at else None,
            "last_error": src.last_error,
            "fetched_today": fetched_today,
        })

    # 累计运行时间：从系统首次上线算起（跨重启持久化），不是本次进程启动到现在。
    # 首次调用时才 seed 一次，起点取「本次进程启动」与「库里最早业务记录」中更早的那个。
    first_started_at = get_first_started_at()
    if first_started_at is None:
        candidates = [_SERVER_START_TIME]
        for column in (HotEvent.first_seen_at, Article.fetched_at):
            earliest = db.query(func.min(column)).scalar()
            if earliest is not None:
                candidates.append(
                    earliest if earliest.tzinfo else earliest.replace(tzinfo=timezone.utc)
                )
        first_started_at = init_first_started_at(min(candidates))

    now_utc = datetime.now(timezone.utc)
    uptime_seconds = max(int((now_utc - first_started_at).total_seconds()), 0)

    return {
        "first_started_at": first_started_at.isoformat(),
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


@router.post("/trigger-fetch", dependencies=[Depends(require_write)])
async def trigger_fetch():
    """Manually trigger the article fetch task."""
    last_fetch = get_last_fetch_time()

    # Check cooldown: if fetch was triggered within last 5 minutes, return success early
    if last_fetch and (datetime.now(timezone.utc) - last_fetch).total_seconds() < FETCH_COOLDOWN_SECONDS:
        _append_log("fetch_task", "success", "Cooldown: skipped, fetch was triggered within last 5 minutes")
        return {"status": "ok", "message": "Fetch already triggered recently, skipping"}

    try:
        set_last_fetch_time()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fetch_task)
        _append_log("fetch_task", "success", "Manually triggered fetch completed")
        return {"status": "ok", "message": "Fetch task triggered successfully"}
    except Exception as e:
        logger.error(f"Manual fetch trigger failed: {e}")
        _append_log("fetch_task", "error", str(e))
        raise HTTPException(status_code=500, detail="Fetch task failed")


@router.post("/trigger-ai", dependencies=[Depends(require_write)])
async def trigger_ai():
    """Manually trigger the AI processing task."""
    last_ai = get_last_ai_time()

    # Check cooldown: if AI was triggered within last 5 minutes, return success early
    if last_ai and (datetime.now(timezone.utc) - last_ai).total_seconds() < AI_COOLDOWN_SECONDS:
        _append_log("ai_process_task", "success", "Cooldown: skipped, AI process was triggered within last 5 minutes")
        return {"status": "ok", "message": "AI process already triggered recently, skipping"}

    try:
        set_last_ai_time()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ai_process_task)
        _append_log("ai_process_task", "success", "Manually triggered AI process completed")
        return {"status": "ok", "message": "AI process task triggered successfully"}
    except Exception as e:
        logger.error(f"Manual AI trigger failed: {e}")
        _append_log("ai_process_task", "error", str(e))
        raise HTTPException(status_code=500, detail="AI process task failed")


@router.get("/logs", dependencies=[Depends(require_read)])
def get_logs(limit: int = 100) -> List[dict]:
    """Get recent task execution logs."""
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000
    return list(_TASK_LOGS)[-limit:]
