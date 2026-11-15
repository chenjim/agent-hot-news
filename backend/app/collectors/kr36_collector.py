import time
from datetime import datetime, timezone
from typing import List

import httpx
from loguru import logger

from app.collectors.base import BaseCollector, RawArticle

# 36氪快讯接口。官网 RSS（https://36kr.com/feed）已失效：请求会返回一个
# 反爬验证 HTML 页面，feedparser 解析出 0 条且不抛异常，监控上看像是「正常」。
# 这里改走官网网页端用的网关接口，POST JSON 直接拿到快讯列表。
KR36_NEWSFLASH_API = "https://gateway.36kr.com/api/mis/nav/newsflash/flow"
KR36_DETAIL_URL = "https://36kr.com/detail_newsflash?itemId={item_id}"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class Kr36Collector(BaseCollector):
    """36氪快讯采集器。"""

    async def fetch(self) -> List[RawArticle]:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://36kr.com",
            "Referer": "https://36kr.com/",
        }
        headers.update(self.extra_config.get("headers") or {})

        page_size = self.extra_config.get("page_size", 30)
        payload = {
            "partner_id": "wap",
            "param": {
                "pageSize": page_size,
                "pageEvent": 0,
                "pageCallback": "",
                "siteId": 1,
                "platformId": 2,
            },
            "timestamp": int(time.time() * 1000),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    KR36_NEWSFLASH_API, json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            raise Exception(f"36kr newsflash fetch failed for {self.name}: {e}")

        if data.get("code") != 0:
            raise Exception(
                f"36kr newsflash API error for {self.name}: "
                f"code={data.get('code')} msg={data.get('msg')}"
            )

        items = (data.get("data") or {}).get("itemList") or []
        if not items:
            # 接口正常但 0 条，通常是接口改版或风控，直接报错让来源状态变红。
            raise Exception(f"36kr newsflash returned 0 items for {self.name}")

        articles: List[RawArticle] = []
        for item in items:
            material = item.get("templateMaterial") or {}
            title = (material.get("widgetTitle") or "").strip()
            if not title:
                continue

            item_id = item.get("itemId") or material.get("itemId")
            url = KR36_DETAIL_URL.format(item_id=item_id) if item_id else ""
            if not url:
                continue

            publish_ms = material.get("publishTime")
            published_at = (
                datetime.fromtimestamp(publish_ms / 1000, tz=timezone.utc)
                if isinstance(publish_ms, (int, float))
                else None
            )

            articles.append(
                RawArticle(
                    url=url,
                    title=title,
                    summary=(material.get("widgetContent") or "").strip() or None,
                    published_at=published_at,
                    source_name=self.name,
                    source_url=self.endpoint,
                    language=self.extra_config.get("language", "zh"),
                )
            )

        logger.info(f"[{self.name}] Parsed {len(articles)} newsflash items")
        return articles
