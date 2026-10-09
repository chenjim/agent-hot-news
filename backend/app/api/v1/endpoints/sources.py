from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_read, require_write
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.models import Source, SourceStatus, SourceType
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate

router = APIRouter()


@router.get("", response_model=List[SourceRead], dependencies=[Depends(require_read)])
def list_sources(
    status: SourceStatus = None,
    db: Session = Depends(get_db),
):
    query = db.query(Source)
    if status:
        query = query.filter(Source.status == status)
    return query.order_by(Source.created_at.desc()).all()


@router.post("", response_model=SourceRead, dependencies=[Depends(require_write)])
def create_source(
    source_in: SourceCreate,
    db: Session = Depends(get_db),
):
    source = Source(**source_in.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/{source_id}", response_model=SourceRead, dependencies=[Depends(require_read)])
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceRead, dependencies=[Depends(require_write)])
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


@router.delete("/{source_id}", dependencies=[Depends(require_write)])
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


@router.post("/{source_id}/fetch", dependencies=[Depends(require_write)])
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

        # 原文不入库：先把带原文的条目交给 LLM 做摘要，失败的跳过。
        # 摘要前先去重，已在库的条目不再重复过 LLM（省 token）。
        from app.ai_pipeline.article_summarizer import ArticleSummarizer

        existing = manager.load_existing(articles)
        articles = await ArticleSummarizer().process(
            articles, is_known=manager.known_predicate(*existing)
        )
        new_count = manager.save_articles(articles, existing=existing)

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
