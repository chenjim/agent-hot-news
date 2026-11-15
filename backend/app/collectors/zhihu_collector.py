import httpx
import re
from typing import List
from app.collectors.base import BaseCollector, RawArticle
from app.utils.cookies import load_cookie
from loguru import logger


# 热榜 target.url 现在给的是 API 地址（如 https://api.zhihu.com/questions/123），
# 浏览器直接打开只会返回 {"error":{"message":"请求参数异常，请升级客户端后重试。","code":10003}}。
# 按 type/id 还原成用户能访问的网页地址。
_API_URL_RE = re.compile(r"^https?://api\.zhihu\.com/(questions|answers|articles)/(\d+)/?$")
_WEB_URL_TPL = {
    "questions": "https://www.zhihu.com/question/{id}",
    "answers": "https://www.zhihu.com/answer/{id}",
    "articles": "https://zhuanlan.zhihu.com/p/{id}",
}


def _web_url(target: dict) -> str:
    """把热榜 target 还原为可浏览的知乎网页链接。"""
    url = (target.get("url") or "").strip()
    m = _API_URL_RE.match(url)
    if m:
        return _WEB_URL_TPL[m.group(1)].format(id=m.group(2))

    # url 缺失时按 type + id 兜底
    t = (target.get("type") or "").lower()
    tid = target.get("id")
    if not url and tid:
        key = {"question": "questions", "answer": "answers", "article": "articles"}.get(t)
        if key:
            return _WEB_URL_TPL[key].format(id=tid)
    return url


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

        # 热榜走 api.zhihu.com，匿名即可 200；www.zhihu.com/api/v3 那条要登录态，
        # 而且附上过期的 z_c0 会被网关判 ERR_TICKET_NOT_EXIST 直接 401。
        # 所以默认不发 cookie.zhihu.txt，确实需要登录态时在 source.config 里开 use_cookie。
        if self.extra_config.get("use_cookie"):
            cookie = load_cookie("zhihu")
            if cookie:
                headers["Cookie"] = cookie
            else:
                logger.warning(f"[{self.name}] use_cookie 打开但没找到 cookie.zhihu.txt")

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
                url = _web_url(target)
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
