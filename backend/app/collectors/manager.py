from typing import List, Type, Dict
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, RawArticle
from app.collectors.rss_collector import RSSCollector
from app.collectors.api_collector import APICollector
from app.collectors.github_trending_collector import GitHubTrendingCollector
from app.collectors.juejin_collector import JuejinCollector
from app.collectors.zhihu_collector import ZhihuCollector
from app.collectors.weibo_hot_collector import WeiboHotCollector
from app.collectors.tianapi_collector import TianapiCollector
from app.collectors.hackernews_collector import HackerNewsCollector
from app.collectors.baidu_hot_collector import BaiduHotCollector
from app.models.models import Source, SourceType, SourceStatus
from sqlalchemy.orm import Session


COLLECTOR_REGISTRY: Dict[SourceType, Type[BaseCollector]] = {
    SourceType.RSS: RSSCollector,
    SourceType.API: APICollector,
    SourceType.SCRAPER: GitHubTrendingCollector,
}

# Additional per-source overrides can be handled by endpoint or name mapping if needed.
# For Juejin/Zhihu/Weibo we register them as API/SCRAPER via their source type,
# but since they have custom collectors we keep a name-based override map.
NAME_COLLECTOR_MAP: Dict[str, Type[BaseCollector]] = {
    "github_trending": GitHubTrendingCollector,
    "juejin": JuejinCollector,
    "zhihu": ZhihuCollector,
    "weibo": WeiboHotCollector,
    "tianapi_douyinhot": TianapiCollector,
    "tianapi_internet": TianapiCollector,
    "tianapi_networkhot": TianapiCollector,
    "tianapi_weibohot": TianapiCollector,
    "Hacker News": HackerNewsCollector,
    "baidu_hot": BaiduHotCollector,
}


class CollectorManager:
    def __init__(self, db: Session):
        self.db = db

    def get_active_sources(self) -> List[Source]:
        """Return all sources that should be fetched (active or previously failed)."""
        return (
            self.db.query(Source)
            .filter(Source.status != SourceStatus.PAUSED)
            .all()
        )

    def create_collector(self, source: Source) -> BaseCollector:
        # Prefer name-based mapping for custom collectors
        collector_cls = NAME_COLLECTOR_MAP.get(source.name)
        if not collector_cls:
            collector_cls = COLLECTOR_REGISTRY.get(source.type)
        if not collector_cls:
            raise ValueError(f"No collector registered for type: {source.type} (name: {source.name})")

        config = {
            "name": source.name,
            "endpoint": source.endpoint,
            "config": source.config or {},
        }
        return collector_cls(config)

    async def _fetch_single_source(self, source: Source) -> List[RawArticle]:
        """Fetch articles from a single source and update its status."""
        from loguru import logger

        try:
            collector = self.create_collector(source)
            articles = await collector.fetch()
            logger.info(f"[{source.name}] Fetched {len(articles)} articles")

            # Update last_fetched_at
            source.last_fetched_at = datetime.now(timezone.utc)
            source.status = SourceStatus.ACTIVE
            source.last_error = None
            return articles
        except Exception as e:
            logger.error(f"[{source.name}] Fetch failed: {e}")
            source.status = SourceStatus.ERROR
            source.last_error = str(e)
            return []

    async def fetch_all(self) -> List[RawArticle]:
        """Fetch articles from all active sources in parallel."""
        import asyncio
        from loguru import logger

        sources = self.get_active_sources()
        if not sources:
            logger.info("No active sources to fetch")
            return []

        semaphore = asyncio.Semaphore(5)

        async def fetch_with_limit(source: Source) -> List[RawArticle]:
            async with semaphore:
                return await self._fetch_single_source(source)

        results = await asyncio.gather(
            *[fetch_with_limit(s) for s in sources],
            return_exceptions=True,
        )

        all_articles: List[RawArticle] = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            # Exceptions are already logged in _fetch_single_source

        # Single commit for all source updates
        self.db.commit()
        return all_articles
