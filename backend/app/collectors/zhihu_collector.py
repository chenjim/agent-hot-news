import httpx
import re
from typing import List
from app.collectors.base import BaseCollector, RawArticle
from app.utils.cookies import load_cookie
from loguru import logger


class ZhihuCollector(BaseCollector):
    """Collect hot list from Zhihu (知乎)."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.zhihu.com/hot",
        }

        cookie = load_cookie("zhihu")
        if cookie:
            headers["Cookie"] = cookie
        else:
            logger.warning(f"[{self.name}] No cookie.zhihu.txt found, fetch may fail")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.endpoint, headers=headers)
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"Zhihu fetch failed for {self.name}: {e}")

        data = response.json()
        items = data.get("data", [])

        for idx, wrapper in enumerate(items):
            try:
                target = wrapper.get("target")
                if not target:
                    continue

                title = target.get("title", "").strip()
                url = target.get("url", "")
                excerpt = target.get("excerpt", "") or target.get("detail", "")

                if not title:
                    continue

                # Normalize URL
                if url and not url.startswith("http"):
                    url = f"https://www.zhihu.com{url}"

                hot_value = wrapper.get("detail_text", "")
                raw_hot_score = 0.0
                m = re.search(r"([\d,]+\.?\d*)\s*万?", hot_value)
                if m:
                    try:
                        num = float(m.group(1).replace(",", ""))
                        raw_hot_score = num * 10000 if "万" in hot_value else num
                    except ValueError:
                        pass

                articles.append(
                    RawArticle(
                        url=self._normalize_url(url) if url else "",
                        title=title,
                        summary=excerpt[:1000] if excerpt else None,
                        source_name=self.name,
                        source_url=self.endpoint,
                        raw_hot_score=raw_hot_score,
                        language=self.extra_config.get("language", "zh"),
                        extra={"rank": idx + 1, "hot_text": hot_value},
                    )
                )
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to parse item {idx}: {e}")
                continue

        logger.info(f"[{self.name}] Parsed {len(articles)} hot items")
        return articles
