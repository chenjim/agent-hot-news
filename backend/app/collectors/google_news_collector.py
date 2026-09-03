import os

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from urllib.parse import urljoin
from app.collectors.base import BaseCollector, RawArticle
from loguru import logger

# 代理只走环境变量（compose 已注入运行时代理），无则直连；
# py 内不硬编码任何代理地址
PROXY = (
    os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
    or None
)


class GoogleNewsCollector(BaseCollector):
    """Collect articles from Google News Topics RSS."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        proxies = {"http://": PROXY, "https://": PROXY} if PROXY else None

        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, proxies=proxies
        ) as client:
            try:
                response = await client.get(self.endpoint, headers=headers)
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"Google News fetch failed for {self.name}: {e}")

        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")

        for item in items:
            try:
                title = item.title.get_text(strip=True) if item.title else ""
                link = item.link.get_text(strip=True) if item.link else ""
                pub_text = item.pubDate.get_text(strip=True) if item.pubDate else None

                published = None
                if pub_text:
                    try:
                        # RFC 822 format: "Fri, 15 May 2026 10:00:00 GMT"
                        published = datetime.strptime(pub_text, "%a, %d %b %Y %H:%M:%S %Z")
                    except ValueError:
                        pass

                description = ""
                if item.description:
                    desc_html = item.description.get_text(strip=True)
                    # Strip HTML tags from description
                    desc_soup = BeautifulSoup(desc_html, "html.parser")
                    description = desc_soup.get_text()[:500]

                articles.append(
                    RawArticle(
                        url=self._normalize_url(link),
                        title=title,
                        summary=description or None,
                        published_at=published,
                        source_name=self.name,
                        source_url=self.endpoint,
                        language="zh",
                    )
                )
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to parse item: {e}")
                continue

        logger.info(f"[{self.name}] Parsed {len(articles)} articles")
        return articles