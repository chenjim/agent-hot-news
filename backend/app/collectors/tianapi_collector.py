import asyncio
import httpx
from datetime import datetime
from hashlib import sha256
from time import time
from typing import List
from urllib.parse import quote

from app.collectors.base import BaseCollector, RawArticle
from app.core.config import get_settings


class TianapiCollector(BaseCollector):
    """Collector for Tianapi hot-news endpoints.

    Supports multiple response shapes:
      - result.list  with fields: word, hotindex, label  (douyinhot, networkhot, weibohot)
      - result.newslist with fields: title, url, description, ctime  (internet)
    """

    # Class-level rate limiter: ensure at least 1.5s between requests
    # across all TianapiCollector instances to avoid API throttling.
    _last_request_time: float = 0.0

    async def fetch(self) -> List[RawArticle]:
        _rate_limit_lock = asyncio.Lock()
        async with _rate_limit_lock:
            now = time()
            elapsed = now - TianapiCollector._last_request_time
            if elapsed < 1.5:
                await asyncio.sleep(1.5 - elapsed)
            TianapiCollector._last_request_time = time()
        settings = get_settings()
        key = settings.TIANAPI_KEY
        if not key:
            raise Exception(f"TIANAPI_KEY not configured for source: {self.name}")

        url = f"{self.endpoint}?key={key}"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"Tianapi fetch failed for {self.name}: {e}")

        data = response.json()
        if data.get("code") != 200:
            raise Exception(f"Tianapi error for {self.name}: {data.get('msg')}")

        items: List[dict] = []
        # New format: top-level "newslist" or "list"
        if "newslist" in data:
            items = data["newslist"]
        elif "list" in data:
            items = data["list"]
        else:
            # Legacy format: nested inside "result"
            result = data.get("result", {})
            if isinstance(result, dict):
                if "list" in result:
                    items = result["list"]
                elif "newslist" in result:
                    items = result["newslist"]

        articles: List[RawArticle] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            # Field mapping: TianAPI uses different field names per endpoint
            title = str(
                item.get("hotword")
                or item.get("word")
                or item.get("title", "")
            ).strip()
            if not title:
                continue

            raw_url = item.get("url", "")
            if raw_url:
                article_url = str(raw_url).strip()
            else:
                # Generate a deterministic pseudo-URL for deduplication
                h = sha256(f"{self.name}:{title}".encode()).hexdigest()[:12]
                article_url = f"tianapi://{self.name}/{h}"

            hot_score = (
                item.get("hotwordnum")
                or item.get("hotindex")
                or item.get("hotnum", 0)
                or 0
            )
            # hotwordnum may contain extra text like "演出 1038974", extract number
            if isinstance(hot_score, str):
                import re
                m = re.search(r"(\d+)", hot_score)
                if m:
                    hot_score = m.group(1)
                else:
                    hot_score = 0

            summary = item.get("description") or item.get("digest", "") or None
            if summary:
                summary = str(summary)[:1000]

            published = None
            ctime = item.get("ctime", "")
            if ctime:
                try:
                    published = datetime.strptime(str(ctime)[:16], "%Y-%m-%d %H:%M")
                except ValueError:
                    pass

            try:
                raw_hot_score = float(hot_score) if hot_score else 0.0
            except (ValueError, TypeError):
                raw_hot_score = 0.0

            articles.append(
                RawArticle(
                    url=self._normalize_url(article_url),
                    title=title,
                    summary=summary,
                    published_at=published,
                    source_name=self.name,
                    source_url=self.endpoint,
                    raw_hot_score=raw_hot_score,
                    language=self.extra_config.get("language", "zh"),
                )
            )

        return articles
