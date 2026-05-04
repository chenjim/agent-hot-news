"""Seed default news sources on first startup."""
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import Engine
from app.database import SessionLocal
from app.models.models import Source, SourceType, SourceStatus
from loguru import logger


DEFAULT_SOURCES = [
    {
        "name": "36氪",
        "type": SourceType.RSS,
        "endpoint": "https://36kr.com/feed",
        "config": {"language": "zh"},
    },
    {
        "name": "Hacker News",
        "type": SourceType.API,
        "endpoint": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "config": {
            "language": "en",
            "list_path": "",
            "field_mapping": {
                "title": "title",
                "url": "url",
            },
        },
    },
    {
        "name": "TechCrunch",
        "type": SourceType.RSS,
        "endpoint": "https://techcrunch.com/feed/",
        "config": {"language": "en"},
    },
    {
        "name": "Solidot",
        "type": SourceType.RSS,
        "endpoint": "https://www.solidot.org/index.rss",
        "config": {"language": "zh"},
    },
    {
        "name": "github_trending",
        "type": SourceType.SCRAPER,
        "endpoint": "https://github.com/trending",
        "config": {"language": "en"},
    },
    {
        "name": "juejin",
        "type": SourceType.API,
        "endpoint": "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed",
        "config": {"language": "zh"},
    },
    {
        "name": "zhihu",
        "type": SourceType.API,
        "endpoint": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50",
        "config": {"language": "zh"},
    },
    {
        "name": "weibo",
        "type": SourceType.SCRAPER,
        "endpoint": "https://s.weibo.com/top/summary",
        "config": {"language": "zh"},
    },
    {
        "name": "tianapi_douyinhot",
        "type": SourceType.API,
        "endpoint": "https://apis.tianapi.com/douyinhot/index",
        "config": {"language": "zh"},
    },
    {
        "name": "tianapi_internet",
        "type": SourceType.API,
        "endpoint": "https://apis.tianapi.com/internet/index",
        "config": {"language": "zh"},
    },
    {
        "name": "tianapi_networkhot",
        "type": SourceType.API,
        "endpoint": "https://apis.tianapi.com/networkhot/index",
        "config": {"language": "zh"},
    },
    {
        "name": "tianapi_weibohot",
        "type": SourceType.API,
        "endpoint": "https://apis.tianapi.com/weibohot/index",
        "config": {"language": "zh"},
        "status": SourceStatus.PAUSED,
    },
    {
        "name": "baidu_hot",
        "type": SourceType.SCRAPER,
        "endpoint": "https://top.baidu.com/board?tab=realtime",
        "config": {"language": "zh"},
    },
]


def seed_sources(engine_or_db):
    if isinstance(engine_or_db, Engine):
        from sqlalchemy.orm import sessionmaker
        SessionMaker = sessionmaker(bind=engine_or_db)
        db = SessionMaker()
    else:
        db = engine_or_db

    try:
        # Rename old "36kr" to "36氪" if exists
        old_source = db.query(Source).filter(Source.name == "36kr").first()
        new_exists = db.query(Source).filter(Source.name == "36氪").first()
        if old_source:
            if new_exists:
                db.delete(old_source)
                logger.info("Deleted duplicate source '36kr' (already have '36氪')")
            else:
                old_source.name = "36氪"
                logger.info("Renamed source '36kr' -> '36氪'")
            db.commit()

        existing = {s.name for s in db.query(Source).all()}
        added = 0
        for src_data in DEFAULT_SOURCES:
            if src_data["name"] in existing:
                continue
            source = Source(**src_data)
            db.add(source)
            added += 1
        if added > 0:
            db.commit()
            logger.info(f"Seeded {added} default sources")
        else:
            logger.info("Sources already seeded")
    finally:
        if isinstance(engine_or_db, Engine):
            db.close()


def run_seed():
    db = SessionLocal()
    try:
        seed_sources(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
