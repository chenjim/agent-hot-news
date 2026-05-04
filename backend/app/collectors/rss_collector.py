import httpx
import feedparser
from datetime import datetime
from typing import List
from app.collectors.base import BaseCollector, RawArticle


class RSSCollector(BaseCollector):
    async def fetch(self) -> List[RawArticle]:
        articles = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.endpoint)
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"RSS fetch failed for {self.name}: {e}")

        # Use response.content (bytes) instead of response.text to let feedparser
        # auto-detect encoding correctly. Some RSS feeds declare wrong encoding.
        parsed = feedparser.parse(response.content)

        for entry in parsed.entries:
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            # Extract content/summary
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description

            content = ""
            if hasattr(entry, "content"):
                content = entry.content[0].value if entry.content else ""

            url = entry.link if hasattr(entry, "link") else ""

            articles.append(
                RawArticle(
                    url=self._normalize_url(url),
                    title=entry.title if hasattr(entry, "title") else "",
                    summary=summary[:1000] if summary else None,
                    content=content[:5000] if content else None,
                    published_at=published,
                    source_name=self.name,
                    source_url=self.endpoint,
                    language=self.extra_config.get("language", "zh"),
                )
            )

        return articles
