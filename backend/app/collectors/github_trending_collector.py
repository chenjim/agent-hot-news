import httpx
import re
from datetime import datetime, timezone
from typing import List
from bs4 import BeautifulSoup
from app.collectors.base import BaseCollector, RawArticle
from loguru import logger


class GitHubTrendingCollector(BaseCollector):
    """Collect trending repositories from GitHub."""

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
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.endpoint, headers=headers)
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"GitHub trending fetch failed for {self.name}: {e}")

            soup = BeautifulSoup(response.text, "html.parser")
        article_list = soup.find_all("article", class_="Box-row")
        today = datetime.now(timezone.utc)

        for idx, item in enumerate(article_list):
            try:
                # Extract repo name from h2 > a
                link_tag = item.select_one("h2 a")
                if not link_tag:
                    continue

                repo_path = link_tag.get("href", "").strip().lstrip("/")
                if not repo_path:
                    continue

                title = repo_path  # owner/repo
                url = f"https://github.com/{repo_path}"

                # Description
                desc_tag = item.select_one("p[class*='col-9']")
                summary = desc_tag.get_text(strip=True) if desc_tag else None

                # Today's stars (trending metric) — prefer over total stars
                raw_hot_score = 0.0
                today_stars_tag = item.select_one("span.d-inline-block.float-sm-right")
                if today_stars_tag:
                    text = today_stars_tag.get_text(strip=True)
                    m = re.search(r"([\d,]+)\s*stars?\s+today", text, re.IGNORECASE)
                    if m:
                        try:
                            raw_hot_score = float(m.group(1).replace(",", ""))
                        except ValueError:
                            pass

                # Fallback to total stars if today's stars not found
                if raw_hot_score == 0.0:
                    stars_tag = item.select_one("a[href$='/stargazers']")
                    if stars_tag:
                        stars_text = stars_tag.get_text(strip=True).replace(",", "")
                        try:
                            raw_hot_score = float(stars_text)
                        except ValueError:
                            pass

                articles.append(
                    RawArticle(
                        url=self._normalize_url(url),
                        title=title,
                        summary=summary,
                        content=summary,
                        source_name=self.name,
                        source_url=self.endpoint,
                        published_at=today,
                        raw_hot_score=raw_hot_score,
                        language=self.extra_config.get("language", "en"),
                        extra={"rank": idx + 1},
                    )
                )
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to parse item {idx}: {e}")
                continue

        logger.info(f"[{self.name}] Parsed {len(articles)} trending repos")
        return articles
