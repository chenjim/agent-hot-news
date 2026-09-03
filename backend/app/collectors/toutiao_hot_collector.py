import httpx
from typing import List
from app.collectors.base import BaseCollector, RawArticle
from app.utils.cookies import load_cookie
from loguru import logger


class ToutiaoHotCollector(BaseCollector):
    """Collect hot board from Toutiao (头条热榜)."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.toutiao.com/",
        }

        cookie = load_cookie("toutiao")
        if cookie:
            headers["Cookie"] = cookie

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.endpoint, headers=headers)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                raise Exception(f"Toutiao hot fetch failed for {self.name}: {e}")

            hot_list = data.get("data", [])
            if not hot_list:
                logger.warning(f"[{self.name}] No hot items found")
                return articles

            for idx, item in enumerate(hot_list):
                try:
                    title = item.get("Title", "")
                    if not title:
                        continue

                    url = item.get("Url", "")
                    if not url:
                        url = f"https://www.toutiao.com/trending/{item.get('ClusterIdStr', '')}/"

                    hot_value = float(item.get("HotValue", 0))
                    label = item.get("LabelDesc", "")

                    articles.append(
                        RawArticle(
                            url=url,
                            title=title,
                            summary=label if label else None,
                            source_name=self.name,
                            source_url=self.endpoint,
                            raw_hot_score=hot_value,
                            language=self.extra_config.get("language", "zh"),
                            extra={"rank": idx + 1, "label": label},
                        )
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to parse item {idx}: {e}")
                    continue

        logger.info(f"[{self.name}] Parsed {len(articles)} hot items")
        return articles
