"""把采集到的原文交给 LLM 做摘要 —— 原文一律不入库。

规则
----
1. ``summary + content`` 合计超过 ``ORIGINAL_THRESHOLD``（300 字）→ 过 LLM 摘要，
   成功才落库，且落库时 ``content`` 恒为 NULL。
2. 合计不超过阈值 → 不调 LLM，把 ``content`` 并进 ``summary`` 原样保留，
   ``content`` 同样置 NULL（原文列永远为空）。
3. 榜单条目（只有标题）原样保留，不浪费 LLM 调用。
4. LLM 摘要失败：该条目**跳过不落库**，记录 ERROR 日志；下一轮采集会重新抓到它并重试
   （dedup 按 URL，未落库即不存在，天然重入）。重试在单次调用内带指数退避。

原文输入不截断（只留 ``MAX_INPUT_CHARS`` 安全阀），避免摘要遗漏信息。
"""

import asyncio
from typing import List, Optional

import httpx
from loguru import logger

from app.collectors.base import RawArticle
from app.core.config import get_settings, llm_extra_headers

# 「带原文」判定阈值：summary + content 合计超过 300 字才值得过 LLM；
# 更短的（榜单条目、RSS 导语、仓库描述）原样保留，省掉无谓的调用
ORIGINAL_THRESHOLD = 300
# LLM 输入安全阀：正常文章远小于此，只用来防异常超长源把上下文撑爆
MAX_INPUT_CHARS = 50_000
# 摘要输出：目标 180 字，信息密度优先时最多 300 字（不为凑字数删事实）
SUMMARY_MAX_TOKENS = 1024
CONCURRENCY = 4
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (2, 6, 15)

_SYSTEM_PROMPT = (
    "你是新闻编辑助理。只输出摘要正文，不要标题、不要列表、不要 Markdown、"
    "不要任何解释性前缀或后缀。"
)

_USER_PROMPT = """把下面这篇原文压缩成一段摘要。

要求：
1. 目标 180 字以内；若原文有多条并列关键事实，最多 300 字，信息密度优先，不要为了短而删掉事实
2. 必须保留：人物/机构、数字、时间、结论
3. 只写原文出现过的信息，不补充、不推测、不脑补
4. 语言跟随原文（中文原文写中文，英文原文写英文）
5. 不要评论、不要「据报道」「原文指出」这类套话、不要标题党
6. 不要写「这段摘要本身」的元话语（如「原文未提及」「根据提供的材料」「不作推测」）——只写内容，不写你怎么处理材料
7. 源材料信息不足就短写，严禁为凑够长度注水、重复换说法、写空话
8. 直接输出摘要正文

【标题】{title}

【原文】
{text}"""


def _total_length(raw: RawArticle) -> int:
    return len((raw.summary or "").strip()) + len((raw.content or "").strip())


def is_original(raw: RawArticle) -> bool:
    """判断该条目是否带「值得过 LLM」的原文（合计超过阈值）。"""
    return _total_length(raw) > ORIGINAL_THRESHOLD


def fold_content(raw: RawArticle) -> RawArticle:
    """短文本（合计不超阈值）不调 LLM：把 content 并进 summary，content 置 NULL。

    这样原文列永不落库，短内容也不丢。
    """
    content = (raw.content or "").strip()
    if content:
        summary = (raw.summary or "").strip()
        raw.summary = f"{summary}\n\n{content}" if summary else content
        raw.content = None
    return raw


def original_text(raw: RawArticle) -> str:
    """拼出喂给 LLM 的完整原文（不截断，仅留安全阀）。"""
    summary = (raw.summary or "").strip()
    content = (raw.content or "").strip()
    parts = [p for p in (summary, content) if p]
    text = "\n\n".join(parts)
    if len(text) > MAX_INPUT_CHARS:
        logger.warning(
            f"原文超过安全阀 {MAX_INPUT_CHARS} 字，截断输入: {raw.source_name} {raw.url[:80]}"
        )
        text = text[:MAX_INPUT_CHARS]
    return text


class ArticleSummarizer:
    """单篇原文 → LLM 摘要。复用与 SummarizerService 相同的 LLM 配置。"""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self.model = settings.OPENAI_CHAT_MODEL

    async def summarize_text(self, title: str, text: str) -> Optional[str]:
        """调用 LLM 生成摘要；重试带指数退避，最终失败返回 None。"""
        if not text.strip():
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _USER_PROMPT.format(title=title or "（无标题）", text=text),
                },
            ],
            "temperature": 0.2,
            "max_tokens": SUMMARY_MAX_TOKENS,
            "reasoning_effort": "none",  # 推理模型会吃掉 token，关掉避免正文被截
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Agent Hot News",
            **llm_extra_headers(self.base_url),
        }

        last_error: Optional[str] = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    # 4xx（鉴权/参数错误等）是永久错误，重试无意义
                    logger.error(f"单篇摘要不可重试（HTTP {resp.status_code}），跳过: {title[:60]}")
                    return None
                else:
                    data = resp.json()
                    choices = data.get("choices") or []
                    content = ""
                    if choices:
                        content = (choices[0].get("message") or {}).get("content") or ""
                    content = content.strip()
                    if content:
                        return content
                    last_error = "empty content"
            except Exception as exc:  # noqa: BLE001 - 任何网络/解析错误都走退避重试
                last_error = f"{type(exc).__name__}: {exc}"

            if attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                logger.warning(
                    f"单篇摘要第 {attempt + 1}/{MAX_ATTEMPTS} 次失败（{last_error}），{wait}s 后重试"
                )
                await asyncio.sleep(wait)

        logger.error(f"单篇摘要最终失败（{last_error}）: {title[:60]}")
        return None

    async def process(
        self,
        raw_articles: List[RawArticle],
        is_known=None,
    ) -> List[RawArticle]:
        """把带原文的条目换成 LLM 摘要，返回**可以落库**的条目。

        - 成功：``summary`` = AI 摘要，``content`` = None
        - 失败：整条丢弃（不落库），打 ERROR 日志，下一轮采集重试
        - 无原文的条目（榜单标题等）：原样保留
        - ``is_known(raw)`` 为 True 的条目（已在库）：跳过 LLM，只把 content 并进
          summary 后原样保留，落库时照常刷新热度/采集时间（摘要前去重，省 token）
        """
        if not raw_articles:
            return []

        need: List[RawArticle] = []
        passthrough: List[RawArticle] = []
        queued_keys = set()  # 批内已排队 LLM 的条目，避免同一篇重复调用
        for raw in raw_articles:
            if not is_original(raw):
                # 不够阈值的：不调 LLM，content 并进 summary（content 永不落库）
                passthrough.append(fold_content(raw))
                continue
            if is_known is not None and is_known(raw):
                # 已在库的原文：本轮不再摘要，保留占位供落库更新
                passthrough.append(fold_content(raw))
                continue
            key = (raw.source_name, raw.title, raw.url)
            if key in queued_keys:
                passthrough.append(fold_content(raw))
                continue
            queued_keys.add(key)
            need.append(raw)

        if not need:
            return passthrough

        logger.info(f"原文待摘要 {len(need)} 条 / 共 {len(raw_articles)} 条")
        sem = asyncio.Semaphore(CONCURRENCY)
        results: List[Optional[RawArticle]] = [None] * len(need)

        async def _handle(idx: int, raw: RawArticle) -> None:
            async with sem:
                summary = await self.summarize_text(raw.title, original_text(raw))
            if summary:
                raw.summary = summary
                raw.content = None
                results[idx] = raw
            else:
                logger.error(
                    f"摘要失败，本条跳过不落库: [{raw.source_name}] {raw.title[:60]} ({raw.url[:80]})"
                )

        await asyncio.gather(*(_handle(i, r) for i, r in enumerate(need)))

        kept = [r for r in results if r is not None]
        failed = len(need) - len(kept)
        if failed:
            logger.error(f"原文摘要完成：成功 {len(kept)} 条，失败跳过 {failed} 条（下一轮采集重试）")
        return passthrough + kept
