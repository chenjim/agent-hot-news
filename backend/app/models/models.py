from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.vector_type import VectorType
from app.core.config import get_settings
from datetime import datetime, timezone
import enum

_settings = get_settings()
_EMBEDDING_DIM = _settings.EMBEDDING_DIMENSION


class SourceType(str, enum.Enum):
    RSS = "rss"
    API = "api"
    SCRAPER = "scraper"


class SourceStatus(str, enum.Enum):
    ACTIVE = "active"
    ERROR = "error"
    PAUSED = "paused"


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), unique=True, nullable=False, index=True)
    title = Column(String(512), nullable=False)
    summary = Column(Text)
    content = Column(Text)
    source_name = Column(String(128), nullable=False, index=True)
    source_url = Column(String(2048))
    published_at = Column(DateTime(timezone=True), index=True)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    raw_hot_score = Column(Float, default=0.0)
    language = Column(String(10), default="zh")
    embedding = Column(VectorType(_EMBEDDING_DIM))  # pgvector on PG, JSON fallback on SQLite
    is_processed = Column(Boolean, default=False)

    event_articles = relationship("EventArticle", back_populates="article")


class HotEvent(Base):
    __tablename__ = "hot_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    summary = Column(Text)
    detail = Column(Text)  # AI 生成的详细摘要（150-300字）
    category = Column(String(64), index=True)
    hot_score = Column(Float, default=0.0, index=True)
    trend = Column(String(16), default="stable")  # up, down, stable
    sentiment = Column(String(16))  # positive, negative, neutral
    entities = Column(JSON)  # list of strings
    articles_count = Column(Integer, default=0)
    sources_count = Column(Integer, default=0)
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    cover_image = Column(String(2048))
    embedding_centroid = Column(VectorType(_EMBEDDING_DIM))

    event_articles = relationship("EventArticle", back_populates="event")


class EventArticle(Base):
    __tablename__ = "event_articles"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("hot_events.id", ondelete="CASCADE"), nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    relevance_score = Column(Float, default=1.0)

    event = relationship("HotEvent", back_populates="event_articles")
    article = relationship("Article", back_populates="event_articles")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True)
    type = Column(Enum(SourceType), nullable=False)
    endpoint = Column(String(2048), nullable=False)
    config = Column(JSON, default=dict)  # extra config like headers, selectors
    status = Column(Enum(SourceStatus), default=SourceStatus.ACTIVE)
    last_fetched_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
