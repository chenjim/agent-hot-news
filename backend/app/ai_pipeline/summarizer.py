import asyncio
import json
from typing import List, Dict, Optional
import httpx
from app.core.config import get_settings
from loguru import logger

settings = get_settings()


class SummarizerService:
    """LLM summarization with rate-limit-aware retries."""

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self.model = settings.OPENAI_CHAT_MODEL
        self._sem = asyncio.Semaphore(2)  # max 2 concurrent LLM calls
        self._last_call = 0.0

    async def _wait_if_needed(self):
        """Ensure minimum interval between calls to avoid rate limits."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_call
        min_interval = 3.0  # seconds between calls
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_call = asyncio.get_event_loop().time()

    async def summarize_cluster(
        self,
        titles: List[str],
        summaries: List[str],
    ) -> Dict[str, Optional[str]]:
        content_samples = "\n".join(
            f"- {t}\n  {s[:200]}" for t, s in zip(titles, summaries) if s
        )

        system_prompt = (
            "你是一个新闻分析助手。给定多篇关于同一事件的新闻报道，"
            "提取核心信息并只输出合法 JSON。"
            "不要输出任何推理过程、解释或 Markdown 格式。"
            "直接输出原始 JSON。"
        )

        user_prompt = f"""以下是一组关于同一事件的新闻报道，请分析并只输出 JSON：

{content_samples}

请严格输出以下 JSON 格式，不要添加任何其他内容：
{{
  "title": "...",
  "summary": "...",
  "category": "...",
  "sentiment": "...",
  "entities": ["...", "..."]
}}

要求：
1. title: 用不超过 8 个字概括事件核心
2. summary: 用一句话（不超过 60 字）描述事件
3. category: 必须从 [tech, finance, social, global, other] 中选择最符合的
4. sentiment: 必须从 [positive, negative, neutral] 中选择整体情感倾向
5. entities: 列出事件涉及的关键实体（人物、公司、地点、产品名），最多 5 个
"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Agent Hot News",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self._sem:
                    await self._wait_if_needed()
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limited (429), waiting {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                if not data.get("choices"):
                    raise RuntimeError(f"API returned no choices: {data}")

                raw = data["choices"][0]["message"]["content"].strip()
                if not raw:
                    raise RuntimeError("API returned empty content")

                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()

                if not raw:
                    raise RuntimeError("Empty JSON after extracting code block")

                result = json.loads(raw)

                required_fields = {"title", "summary", "category", "sentiment", "entities"}
                if not required_fields.issubset(result.keys()):
                    missing = required_fields - result.keys()
                    raise RuntimeError(f"Missing required fields: {missing}")

                logger.info(f"Summarized cluster: {result.get('title', 'N/A')}")
                return result

            except Exception as e:
                wait = 2 ** attempt  # 1s, 2s, 4s
                if attempt < max_retries - 1:
                    logger.warning(f"Summarization attempt {attempt + 1} failed: {e}, retry in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Summarization failed after {max_retries} attempts: {e}")

        return {
            "title": titles[0][:20] if titles else "未知事件",
            "summary": summaries[0][:60] if summaries else "暂无摘要",
            "category": "other",
            "sentiment": "neutral",
            "entities": [],
        }
