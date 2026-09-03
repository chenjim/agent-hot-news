import asyncio
import httpx
import feedparser
import os
from datetime import datetime
from typing import List, Optional
from app.collectors.base import BaseCollector, RawArticle
from loguru import logger


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _resolve_proxy(proxy: Optional[str]) -> Optional[str]:
    if proxy:
        return proxy
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        value = os.environ.get(key)
        if value:
            return value
    return None


class RSSCollector(BaseCollector):
    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = self.extra_config.get("headers") or {"User-Agent": DEFAULT_USER_AGENT}
        timeout = self.extra_config.get("timeout", 30.0)
        if isinstance(timeout, (int, float)):
            timeout = httpx.Timeout(timeout, connect=10.0)

        proxy = _resolve_proxy(self.extra_config.get("proxy"))
        client_kwargs = {
            "timeout": timeout,
            "follow_redirects": True,
            "limits": httpx.Limits(max_keepalive_connections=5, max_connections=10),
        }
        if proxy:
            client_kwargs["proxy"] = proxy
            logger.debug(f"Using proxy {proxy} for source {self.name}")

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                response = await client.get(self.endpoint, headers=headers)
                response.raise_for_status()
            except Exception as e:
                err_repr = f"{type(e).__name__}: {repr(e)}"
                raise Exception(f"RSS fetch failed for {self.name}: {err_repr}")

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

            # Prefer guid over link; keep full URL including query string for dedup
            url = ""
            if hasattr(entry, "guid") and entry.guid:
                url = entry.guid.strip()
            elif hasattr(entry, "link") and entry.link:
                link = entry.link.strip()
                if "?" in link:
                    url = link
                else:
                    url = link.rstrip("/")

            articles.append(
                RawArticle(
                    url=url,
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