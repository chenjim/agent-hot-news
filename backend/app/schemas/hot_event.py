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
    # 聚合发布时间：达标瞬间写入、永不更新；列表排序与卡片时间都用它
    aggregated_at: Optional[datetime] = None
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
    # 该链接能否在浏览器里打开：false 时前端用标题做搜索兜底
    browsable: bool = False


class HotEventDetail(HotEventListItem):
    timeline: List[TimelineItem]
    sources: List[SourceItem]
    related_events: List[Dict[str, Any]]
