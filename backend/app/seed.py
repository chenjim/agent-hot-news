"""Seed default news sources on first startup."""
import asyncio
import os
from sqlalchemy.orm import Session
from sqlalchemy import Engine
from app.database import SessionLocal
from app.models.models import Source, SourceType, SourceStatus
from loguru import logger

# 默认代理只走环境变量（compose 已注入运行时代理），无则直连；
# py 内不硬编码任何代理地址，地址统一由环境/compose 管理
# （seed 会把新 config 合并进已存在的 Source 行，改这里即可推送到老库）
_DEFAULT_PROXY = (
    os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
    or None
)

# 36氪官网 RSS（https://36kr.com/feed）已失效，返回反爬 HTML 解析 0 条，
# 统一改走网页端快讯网关接口。
KR36_ENDPOINT = "https://gateway.36kr.com/api/mis/nav/newsflash/flow"

# 知乎热榜：www.zhihu.com/api/v3 那条必须登录态，cookie 一过期就 401
# （ERR_TICKET_NOT_EXIST）；api.zhihu.com 这条匿名可访问，返回结构一致。
ZHIHU_ENDPOINT = "https://api.zhihu.com/topstory/hot-lists/total?limit=50"


DEFAULT_SOURCES = [
    {
        "name": "36氪",
        # 官网 RSS 已失效（返回反爬 HTML，解析 0 条），改走快讯网关接口，
        # 采集器由 NAME_COLLECTOR_MAP 映射到 Kr36Collector。
        "type": SourceType.API,
        "endpoint": KR36_ENDPOINT,
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
        "endpoint": "https://feeds.feedburner.com/solidot",
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
        "endpoint": ZHIHU_ENDPOINT,
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
    {
        "name": "toutiao",
        "type": SourceType.API,
        "endpoint": "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        "config": {"language": "zh"},
    },
    {
        "name": "google_news",
        "type": SourceType.SCRAPER,
        "endpoint": "https://news.google.com/rss/topics/CAAqKggKIiRDQkFTRlFvSUwyMHZNRFZxYUdjU0JYcG9MVU5PR2dKRFRpZ0FQAQ?hl=zh-CN&gl=CN&ceid=CN%3Azh-Hans",
        "config": {"language": "zh"},
    },
    {
        "name": "经济观察网",
        "type": SourceType.RSS,
        "endpoint": "https://www.eeo.com.cn/rss.xml",
        "config": {"language": "zh"},
    },
    {
        "name": "FT中文网",
        "type": SourceType.RSS,
        "endpoint": "https://www.ftchinese.com/rss/news",
        "config": {
            "language": "zh",
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            "timeout": 45.0,
            "proxy": _DEFAULT_PROXY,
        },
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

        existing = {s.name: s for s in db.query(Source).all()}
        added = 0
        updated = 0

        # 老库里的 36氪 仍指向已失效的官网 RSS，把类型和 endpoint 一起迁移过来
        kr36 = existing.get("36氪")
        if kr36 and (kr36.type != SourceType.API or kr36.endpoint != KR36_ENDPOINT):
            kr36.type = SourceType.API
            kr36.endpoint = KR36_ENDPOINT
            updated += 1

        # 老库里的 zhihu 仍指向需要登录态的 www.zhihu.com/api/v3，换成可匿名访问的接口
        zhihu = existing.get("zhihu")
        if zhihu and zhihu.endpoint != ZHIHU_ENDPOINT:
            zhihu.type = SourceType.API
            zhihu.endpoint = ZHIHU_ENDPOINT
            updated += 1

        for src_data in DEFAULT_SOURCES:
            source = existing.get(src_data["name"])
            if source is None:
                source = Source(**src_data)
                db.add(source)
                added += 1
            else:
                # Merge latest default config so that new fields (e.g. proxy,
                # headers, timeout) are propagated to existing installations.
                new_config = dict(src_data.get("config") or {})
                if source.config != new_config:
                    source.config = new_config
                    updated += 1
        if added > 0 or updated > 0:
            db.commit()
            logger.info(f"Seeded {added} new sources, updated {updated} existing sources")
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
