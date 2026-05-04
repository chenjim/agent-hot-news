from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.models import Source, SourceStatus, SourceType
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate

router = APIRouter()


@router.get("", response_model=List[SourceRead])
def list_sources(
    status: SourceStatus = None,
    db: Session = Depends(get_db),
):
    query = db.query(Source)
    if status:
        query = query.filter(Source.status == status)
    return query.order_by(Source.created_at.desc()).all()


@router.post("", response_model=SourceRead)
def create_source(
    source_in: SourceCreate,
    db: Session = Depends(get_db),
):
    source = Source(**source_in.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceRead)
def update_source(
    source_id: int,
    source_in: SourceUpdate,
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    for field, value in source_in.model_dump(exclude_unset=True).items():
        setattr(source, field, value)

    db.commit()
    db.refresh(source)
    return source


@router.delete("/{source_id}")
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"ok": True}


@router.post("/{source_id}/fetch")
async def trigger_source_fetch(
    source_id: int,
    db: Session = Depends(get_db),
):
    """Manually trigger fetch for a single source."""
    from app.collectors.manager import CollectorManager
    from app.api.v1.endpoints.admin import _append_log
    from app.models.models import Article

    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        manager = CollectorManager(db)
        collector = manager.create_collector(source)
        articles = await collector.fetch()

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

        # Update source timestamp
        source.last_fetched_at = datetime.now(timezone.utc)
        db.commit()

        _append_log("fetch_task", "success", f"Source {source.name}: {new_count} new articles")
        return {"status": "ok", "fetched": len(articles), "new": new_count}
    except Exception as e:
        db.rollback()
        source.status = SourceStatus.ERROR
        source.last_error = str(e)
        db.commit()
        _append_log("fetch_task", "failed", f"Source {source.name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fetch failed: {e}")
