import httpx
from typing import List
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, RawArticle
from loguru import logger


class JuejinCollector(BaseCollector):
    """Collect hot articles from Juejin (掘金)."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "page_type": 0,
            "cursor": "0",
            "limit": 30,
            "sort_type": 200,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.endpoint, headers=headers, json=payload
                )
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"Juejin fetch failed for {self.name}: {e}")

        data = response.json()
        items = data.get("data", [])

        for idx, wrapper in enumerate(items):
            try:
                item_info = wrapper.get("item_info")
                if not item_info:
                    continue

                article_info = item_info.get("article_info", {})
                title = article_info.get("title", "").strip()
                article_id = article_info.get("article_id", "")

                if not title or not article_id:
                    continue

                url = f"https://juejin.cn/post/{article_id}"
                summary = article_info.get("brief_content", "") or None
                hot_value = article_info.get("view_count", 0) or article_info.get("digg_count", 0)

                # Parse ctime (creation timestamp in seconds)
                ctime = article_info.get("ctime")
                published = None
                if ctime:
                    try:
                        published = datetime.fromtimestamp(int(ctime), tz=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    RawArticle(
                        url=self._normalize_url(url),
                        title=title,
                        summary=summary[:1000] if summary else None,
                        source_name=self.name,
                        source_url=self.endpoint,
                        published_at=published,
                        raw_hot_score=float(hot_value) if hot_value else 0.0,
                        language=self.extra_config.get("language", "zh"),
                        extra={"rank": idx + 1},
                    )
                )
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to parse item {idx}: {e}")
                continue

        logger.info(f"[{self.name}] Parsed {len(articles)} articles")
        return articles
