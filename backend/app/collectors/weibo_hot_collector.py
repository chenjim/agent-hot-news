import httpx
import re
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from app.collectors.base import BaseCollector, RawArticle
from app.utils.cookies import load_cookie
from loguru import logger


class WeiboHotCollector(BaseCollector):
    """Collect hot search list from Weibo (微博)."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://s.weibo.com/",
        }

        cookie = load_cookie("weibo")
        if cookie:
            headers["Cookie"] = cookie
        else:
            logger.warning(f"[{self.name}] No cookie.weibo.txt found, fetch may fail")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.endpoint, headers=headers)
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"Weibo hot fetch failed for {self.name}: {e}")

            soup = BeautifulSoup(response.text, "html.parser")
        tbody = soup.find("tbody")
        if not tbody:
            logger.warning(f"[{self.name}] No tbody found in page")
            return articles

        rows = tbody.find_all("tr")
        for row in rows:
            try:
                rank_tag = row.find("td", class_="ranktop")
                if not rank_tag:
                    continue

                rank = rank_tag.get_text(strip=True)
                if not rank.isdigit():
                    continue

                title_tag = row.find("a", href=True)
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                if not title:
                    continue

                hot_tag = row.find("span")
                hot_value = 0.0
                if hot_tag:
                    hot_text = hot_tag.get_text(strip=True)
                    try:
                        hot_value = float(hot_text)
                    except ValueError:
                        pass

                encoded_title = quote(title)
                url = f"https://s.weibo.com/weibo?q={encoded_title}"

                articles.append(
                    RawArticle(
                        url=url,
                        title=title,
                        summary=None,
                        source_name=self.name,
                        source_url=self.endpoint,
                        raw_hot_score=hot_value,
                        language=self.extra_config.get("language", "zh"),
                        extra={"rank": int(rank), "hot_value": hot_value},
                    )
                )
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to parse row: {e}")
                continue

        logger.info(f"[{self.name}] Parsed {len(articles)} hot search items")
        return articles
