from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class ArticleRead(BaseModel):
    id: int
    url: str
    title: str
    summary: Optional[str] = None
    source_name: str
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    raw_hot_score: float
    language: str
    is_processed: bool

    class Config:
        from_attributes = True
