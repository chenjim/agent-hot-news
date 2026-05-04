import httpx
from typing import List
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, RawArticle
from loguru import logger


class HackerNewsCollector(BaseCollector):
    """Collect top stories from Hacker News.

    HN API returns a list of story IDs from /v0/topstories.json.
    Each story detail is fetched from /v0/item/{id}.json.
    """

    BASE_URL = "https://hacker-news.firebaseio.com/v0"
    MAX_STORIES = 30

    async def fetch(self) -> List[RawArticle]:
        articles = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get top story IDs
            resp = await client.get(f"{self.BASE_URL}/topstories.json")
            resp.raise_for_status()
            story_ids = resp.json()

            if not isinstance(story_ids, list):
                raise RuntimeError(f"Unexpected response type: {type(story_ids)}")

            top_ids = story_ids[:self.MAX_STORIES]
            logger.info(f"[{self.name}] Fetched {len(top_ids)} story IDs")

            # Step 2: Fetch each story detail
            for story_id in top_ids:
                try:
                    item_resp = await client.get(f"{self.BASE_URL}/item/{story_id}.json")
                    item_resp.raise_for_status()
                    item = item_resp.json()

                    if not item or not isinstance(item, dict):
                        continue

                    # Skip non-story items (comments, jobs, polls)
                    item_type = item.get("type", "")
                    if item_type != "story":
                        continue

                    title = item.get("title", "").strip()
                    if not title:
                        continue

                    url = item.get("url", "")
                    if not url:
                        # Self-post (Ask HN, Show HN) uses HN discussion URL
                        url = f"https://news.ycombinator.com/item?id={story_id}"

                    score = item.get("score", 0) or 0
                    published = None
                    item_time = item.get("time")
                    if item_time:
                        published = datetime.fromtimestamp(item_time, tz=timezone.utc)

                    articles.append(
                        RawArticle(
                            url=self._normalize_url(url),
                            title=title,
                            summary=None,
                            published_at=published,
                            source_name=self.name,
                            source_url=self.endpoint,
                            raw_hot_score=float(score),
                            language=self.extra_config.get("language", "en"),
                            extra={
                                "hn_id": story_id,
                                "descendants": item.get("descendants", 0),
                                "by": item.get("by", ""),
                            },
                        )
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to fetch story {story_id}: {e}")
                    continue

        logger.info(f"[{self.name}] Parsed {len(articles)} stories")
        return articles
