import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models.models import HotEvent, EventArticle, Article
from app.schemas.hot_event import HotEventListItem, HotEventDetail
from app.cache import cache_response
from app.utils.timezone import get_tz
from app.utils.url_probe import PROBE_TIMEOUT, is_browser_url, probe_many

# 详情接口整体探测预算：单个 5s + 2s 余量，超时则退回「http 即认为可用」
_PROBE_BUDGET = PROBE_TIMEOUT + 2

router = APIRouter()


@router.get("", response_model=List[HotEventListItem])
@cache_response(ttl=60)
async def list_hot_events(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(30, ge=1, le=300),
    offset: int = Query(0, ge=0, description="分页偏移，配合 limit 做无限滚动"),
    db: Session = Depends(get_db),
    tz: str = Query("Asia/Shanghai"),
):
    """Get hot events ordered by aggregated_at desc (聚合发布时间倒序).

    只返回已发布的事件（aggregated_at 非空 = 当时已凑满 MIN_PUBLISH_ARTICLES
    篇文章且来源 ≥ MIN_EVENT_SOURCES），未达标事件不上列表。
    卡片上显示的就是 aggregated_at，排序字段必须与展示字段一致；
    该时间一旦写入永不更新，老事件不会再因追加报道跳回头条。
    ``offset`` 供前端「滑到底部自动加载下一页」翻页用。
    """
    now = datetime.now(get_tz(tz))
    since = now - timedelta(days=7)

    query = (
        db.query(HotEvent)
        .filter(HotEvent.aggregated_at.isnot(None))
        .filter(HotEvent.aggregated_at >= since)
    )
    if category:
        query = query.filter(HotEvent.category == category)

    events = query.order_by(
        HotEvent.aggregated_at.desc(),
        HotEvent.id.desc(),
    ).offset(offset).limit(limit).all()
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
        # published_at 大面积为 NULL（采集源不给发布时间），NULL 在 PG 里 DESC 默认
        # NULLS FIRST，会把没时间的顶到最前面 → 用采集时间 coalesce 兜底排序并展示。
        .order_by(func.coalesce(Article.published_at, Article.fetched_at).desc())
        .all()
    )

    # Build timeline and sources
    timeline = []
    sources = []

    # 来源链接可浏览性：伪 URL 一律 false；http(s) 并行探测一次并缓存（成功 24h / 失败 2h）。
    # 探测不走出站代理，和访客直连一致；超时则退回「是 http 就认为可用」，不让接口挂住。
    try:
        probe = await asyncio.wait_for(
            probe_many([a.url for _, a in event_articles]), timeout=_PROBE_BUDGET
        )
    except Exception:
        probe = {}

    for ea, article in event_articles:
        timeline.append({
            "time": (article.published_at or article.fetched_at).isoformat()
            if (article.published_at or article.fetched_at)
            else None,
            "source": article.source_name,
            "title": article.title,
        })
        # 不返回原文 content：原文不入库，接口也不透出（详见 docs/api.md）
        browsable = bool(probe.get(article.url, is_browser_url(article.url)))
        sources.append({
            "name": article.source_name,
            "url": article.url,
            "title": article.title,
            "hot_score": article.raw_hot_score,
            "browsable": browsable,
        })

    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "detail": event.detail,
        "category": event.category,
        "hot_score": event.hot_score,
        "trend": event.trend,
        "sentiment": event.sentiment,
        "entities": event.entities,
        "articles_count": event.articles_count,
        "sources_count": event.sources_count,
        "first_seen_at": event.first_seen_at,
        "last_updated_at": event.last_updated_at,
        "aggregated_at": event.aggregated_at,
        "cover_image": event.cover_image,
        "timeline": timeline,
        "sources": sources,
        "related_events": [],  # TODO: implement related events
    }
