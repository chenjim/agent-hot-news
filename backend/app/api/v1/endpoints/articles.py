from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.models import Article
from app.schemas.article import ArticleRead

router = APIRouter()


@router.get("", response_model=List[ArticleRead])
def list_articles(
    source_name: Optional[str] = Query(None),
    is_processed: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Article)
    if source_name:
        query = query.filter(Article.source_name == source_name)
    if is_processed is not None:
        query = query.filter(Article.is_processed == is_processed)

    return query.order_by(Article.fetched_at.desc()).offset(offset).limit(limit).all()
