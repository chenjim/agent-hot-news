import httpx
import re
from typing import List
from urllib.parse import unquote, parse_qs, urlparse
from bs4 import BeautifulSoup
from app.collectors.base import BaseCollector, RawArticle
from app.utils.cookies import load_cookie
from loguru import logger


class BaiduHotCollector(BaseCollector):
    """Collect hot search list from Baidu (百度热搜)."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        cookie = load_cookie("baidu")
        if cookie:
            headers["Cookie"] = cookie
        else:
            logger.warning(f"[{self.name}] No cookie.baidu.txt found")

        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True
        ) as client:
            try:
                response = await client.get(
                    self.endpoint, headers=headers
                )
                response.raise_for_status()
            except Exception as e:
                raise Exception(
                    f"Baidu hot fetch failed for {self.name}: {e}"
                )

            soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select(".category-wrap_iQLoo")
        if not cards:
            logger.warning(f"[{self.name}] No hot cards found")
            return articles

        for idx, card in enumerate(cards):
            try:
                link = card.select_one("a.img-wrapper_29V76")
                if not link:
                    continue

                href = link.get("href", "")
                parsed = urlparse(href)
                query = parse_qs(parsed.query)
                title = ""
                if "wd" in query:
                    title = unquote(query["wd"][0])
                if not title:
                    continue

                rank_tag = card.select_one(".index_1Ew5p")
                rank = 0
                if rank_tag:
                    rank_text = rank_tag.get_text(strip=True)
                    m = re.search(r"\d+", rank_text)
                    if m:
                        rank = int(m.group())

                hot_tag = card.select_one(".hot-index_1Bl1a")
                raw_hot_score = 0.0
                if hot_tag:
                    hot_text = hot_tag.get_text(strip=True)
                    hot_text = hot_text.replace(",", "").replace(" ", "")
                    try:
                        raw_hot_score = float(hot_text)
                    except ValueError:
                        pass

                # Baidu search URLs are differentiated by the ?wd= query param;
                # _normalize_url() strips the query string, which collapses every
                # search link into the same URL. Use the full href instead.
                article_url = href.strip() if href else f"baidu://{self.name}/{quote(title)}"

                articles.append(
                    RawArticle(
                        url=article_url,
                        title=title,
                        summary=None,
                        source_name=self.name,
                        source_url=self.endpoint,
                        raw_hot_score=raw_hot_score,
                        language=self.extra_config.get("language", "zh"),
                        extra={"rank": rank},
                    )
                )
            except Exception as e:
                logger.warning(
                    f"[{self.name}] Failed to parse card {idx}: {e}"
                )
                continue

        logger.info(
            f"[{self.name}] Parsed {len(articles)} hot search items"
        )
        return articles
