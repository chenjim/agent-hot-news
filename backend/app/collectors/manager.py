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
from app.collectors.google_news_collector import GoogleNewsCollector
from app.collectors.toutiao_hot_collector import ToutiaoHotCollector
from app.models.models import Source, SourceType, SourceStatus, Article
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
    "toutiao": ToutiaoHotCollector,
    "tianapi_douyinhot": TianapiCollector,
    "tianapi_internet": TianapiCollector,
    "tianapi_networkhot": TianapiCollector,
    "tianapi_weibohot": TianapiCollector,
    "Hacker News": HackerNewsCollector,
    "baidu_hot": BaiduHotCollector,
    "google_news": GoogleNewsCollector,
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

        semaphore = asyncio.Semaphore(3)

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

    def load_existing(self, raw_articles: List[RawArticle]):
        """取出本批中「已在库」的文章索引，供摘要前去重与 save_articles 共用。

        返回 ``(existing_by_url, existing_by_source_title)``，判定口径与
        ``save_articles`` 完全一致：URL 精确匹配，或（来源名 + 标题）匹配。
        摘要前用它跳过已在库的条目，避免每轮采集重复过 LLM。
        """
        if not raw_articles:
            return {}, {}

        urls = {raw.url for raw in raw_articles}
        existing_by_url = {
            a.url: a
            for a in self.db.query(Article).filter(Article.url.in_(urls)).all()
        }

        # Also query existing articles by (source_name, title) to catch
        # duplicates that arrived under different URLs.
        from sqlalchemy import or_, and_

        pairs = {(raw.source_name, raw.title) for raw in raw_articles}
        conditions = [
            and_(Article.source_name == sn, Article.title == t) for sn, t in pairs
        ]
        existing_by_source_title = {
            (a.source_name, a.title): a
            for a in self.db.query(Article).filter(or_(*conditions)).all()
        }
        return existing_by_url, existing_by_source_title

    @staticmethod
    def known_predicate(existing_by_url, existing_by_source_title):
        """把 ``load_existing`` 的结果包成 ``raw -> bool`` 谓词（该条目是否已在库）。"""

        def _is_known(raw: RawArticle) -> bool:
            return (
                raw.url in existing_by_url
                or (raw.source_name, raw.title) in existing_by_source_title
            )

        return _is_known

    def save_articles(
        self,
        raw_articles: List[RawArticle],
        existing=None,
    ) -> int:
        """Save new articles and update timestamps for existing ones.

        Deduplication is performed on two levels:
        1. By URL (exact match after normalization).
        2. By (source_name, title) — prevents the same headline from the same
           source being stored under different URLs (e.g. tracking links,
           syndicated copies on different domains).

        For existing articles, updates ``fetched_at``, ``raw_hot_score`` and
        back-fills ``published_at`` when missing.

        ``existing`` 可选：``load_existing`` 的返回值。摘要前去重已经查过一次时传进来，
        避免重复构建同一批 OR 条件。不传则自行查询（兼容旧调用）。

        Returns the number of newly created articles.
        """
        seen_urls = set()
        seen_source_titles = set()
        new_count = 0

        if existing is None:
            existing_by_url, existing_by_source_title = self.load_existing(
                raw_articles
            )
        else:
            existing_by_url, existing_by_source_title = existing

        for raw in raw_articles:
            # 1. Deduplicate within the same batch by URL
            if raw.url in seen_urls:
                continue
            seen_urls.add(raw.url)

            # 2. Deduplicate within the same batch by (source_name, title)
            st_key = (raw.source_name, raw.title)
            if st_key in seen_source_titles:
                continue
            seen_source_titles.add(st_key)

            # 3. Match by URL first
            existing = existing_by_url.get(raw.url)
            if existing:
                existing.fetched_at = datetime.now(timezone.utc)
                existing.raw_hot_score = raw.raw_hot_score
                if raw.published_at is not None and existing.published_at is None:
                    existing.published_at = raw.published_at
                continue

            # 4. Match by (source_name, title) — same headline, different URL
            existing = existing_by_source_title.get(st_key)
            if existing:
                existing.fetched_at = datetime.now(timezone.utc)
                existing.raw_hot_score = raw.raw_hot_score
                if raw.published_at is not None and existing.published_at is None:
                    existing.published_at = raw.published_at
                continue

            # 5. Truly new article
            # 落库层硬约束：原文（content）永不入库。上游 ArticleSummarizer 应已把
            # 原文换成 LLM 摘要；若仍有 content 说明调用方漏了处理，这里丢弃并告警。
            if raw.content:
                logger.warning(
                    f"落库时发现未摘要的原文，已丢弃 content: [{raw.source_name}] "
                    f"{raw.title[:60]}"
                )
            article = Article(
                url=raw.url,
                title=raw.title,
                summary=raw.summary,
                content=None,
                source_name=raw.source_name,
                source_url=raw.source_url,
                published_at=raw.published_at,
                raw_hot_score=raw.raw_hot_score,
                language=raw.language,
            )
            self.db.add(article)
            new_count += 1

        return new_count
