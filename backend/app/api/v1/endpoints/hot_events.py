from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models.models import HotEvent, EventArticle, Article
from app.schemas.hot_event import HotEventListItem, HotEventDetail
from app.cache import cache_response
from app.utils.timezone import get_tz

router = APIRouter()


@router.get("", response_model=List[HotEventListItem])
@cache_response(ttl=60)
async def list_hot_events(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    tz: str = Query("Asia/Shanghai"),
):
    """Get hot events ordered by first_seen_at desc (newest first).
    Ordered by is_today desc, then hot_score desc within each group."""
    now = datetime.now(get_tz(tz))
    since = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    query = db.query(HotEvent).filter(HotEvent.last_updated_at >= since)
    if category:
        query = query.filter(HotEvent.category == category)

    # Order by first_seen_at desc (newest first)
    events = query.order_by(
        HotEvent.first_seen_at.desc(),
    ).limit(limit).all()
    return events


@router.get("/{event_id}", response_model=HotEventDetail)
async def get_hot_event_detail(
    event_id: int,
    db: Session = Depends(get_db),
):
    """Get detailed information about a specific hot event."""
    event = db.query(HotEvent).filter(HotEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Load related articles through EventArticle
    event_articles = (
        db.query(EventArticle, Article)
        .join(Article, EventArticle.article_id == Article.id)
        .filter(EventArticle.event_id == event_id)
        .order_by(Article.published_at.desc())
        .all()
    )

    # Build timeline and sources
    timeline = []
    sources = []
    for ea, article in event_articles:
        timeline.append({
            "time": article.published_at.isoformat() if article.published_at else None,
            "source": article.source_name,
            "title": article.title,
        })
        sources.append({
            "name": article.source_name,
            "url": article.url,
            "title": article.title,
            "hot_score": article.raw_hot_score,
        })

    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "category": event.category,
        "hot_score": event.hot_score,
        "trend": event.trend,
        "sentiment": event.sentiment,
        "entities": event.entities,
        "articles_count": event.articles_count,
        "sources_count": event.sources_count,
        "first_seen_at": event.first_seen_at,
        "last_updated_at": event.last_updated_at,
        "cover_image": event.cover_image,
        "timeline": timeline,
        "sources": sources,
        "related_events": [],  # TODO: implement related events
    }
