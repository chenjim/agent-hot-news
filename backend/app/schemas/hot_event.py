from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict, Any


class HotEventListItem(BaseModel):
    id: int
    title: str
    summary: Optional[str] = None
    detail: Optional[str] = None
    category: Optional[str] = None
    hot_score: float
    trend: str
    sentiment: Optional[str] = None
    entities: Optional[List[str]] = None
    articles_count: int
    sources_count: int
    first_seen_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    cover_image: Optional[str] = None

    class Config:
        from_attributes = True


class TimelineItem(BaseModel):
    time: Optional[str]
    source: str
    title: str


class SourceItem(BaseModel):
    name: str
    url: str
    title: str
    hot_score: float
    content: Optional[str] = None


class HotEventDetail(HotEventListItem):
    timeline: List[TimelineItem]
    sources: List[SourceItem]
    related_events: List[Dict[str, Any]]
