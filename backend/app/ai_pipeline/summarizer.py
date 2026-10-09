import asyncio
import json
from typing import List, Dict, Optional
import httpx
from app.core.config import get_settings, llm_extra_headers
from loguru import logger

settings = get_settings()

# 事件分类白名单：LLM 只能从中选。越界或别名一律归一，避免出现前端筛不到的类
# （历史数据里出现过 sports-other 这种前端枚举没有的值）。
ALLOWED_CATEGORIES = (
    "tech",
    "finance",
    "social",
    "global",
    "sports",
    "entertainment",
    "health",
    "other",
)
# 常见越界输出 / 别名 -> 白名单
_CATEGORY_ALIASES = {
    "sport": "sports",
    "sports-other": "sports",
    "sports_other": "sports",
    "entertainment-other": "entertainment",
    "movie": "entertainment",
    "health-other": "health",
}


def normalize_category(value) -> str:
    """把 LLM 返回的分类收敛到 ``ALLOWED_CATEGORIES``，越界一律归 other。"""
    key = str(value or "").strip().lower()
    key = _CATEGORY_ALIASES.get(key, key)
    return key if key in ALLOWED_CATEGORIES else "other"


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
        parts = []
        for t, s in zip(titles, summaries):
            s = (s or "").strip()
            if s:
                parts.append(f"- {t}\n  {s[:600]}")
            else:
                # 只有标题、没有正文：标题本身是材料，不能连行一起丢掉
                # （丢掉会导致 prompt 里材料为空，模型会凭空编造事件）
                parts.append(f"- {t}\n  （无正文，仅有标题）")
        content_samples = "\n".join(parts)

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
  "detail": "...",
  "category": "...",
  "sentiment": "...",
  "entities": ["...", "..."]
}}

要求：
1. title: 用不超过 8 个字概括事件核心
2. summary: 用一句话（不超过 60 字）描述事件
3. detail: 写事件的背景、关键信息、进展和意义，信息密度优先。**下限 20 字**（一两句说清楚即可），
   源材料信息足就写足（通常 80-250 字），信息少就短写，**严禁为了达到长度而注水**。
   禁止出现描述「这段摘要本身」的元话语，例如「根据提供的报道」「报道未提及」「不进行任何推测」
   「仅此核心信息」「无额外深度扩展」「据报道」等 —— 只写事件本身，不写你怎么处理材料的
4. category: 必须从 [tech, finance, social, global, sports, entertainment, health, other] 中选择最符合的
   （tech=科技互联网，finance=财经商业，social=社会民生/案件/时政，global=国际，
   sports=体育赛事，entertainment=娱乐八卦影视，health=健康医疗，other=其他）
5. sentiment: 必须从 [positive, negative, neutral] 中选择整体情感倾向
   （情感只填这个字段，detail 里不要重复描述事件的情感倾向）
6. entities: 列出事件涉及的关键实体（人物、公司、地点、产品名、事件名、技术名），要简洁，最多 5 个

重要约束：
- 上面列出的材料是**唯一信息来源**，标题也算材料
- 若某条标了「无正文，仅有标题」，只能依据标题里出现的事实写，严禁引入标题之外的人物、公司、产品、地点、数字
- 材料完全支撑不了细节时就只写标题能说清的一句话（约 20 字），宁可短，绝不编造
- 禁止编造或猜测具体年份、日期、数字等细节，除非源材料明确提到
- 若来源未给出具体时间，使用"近日""近期"等模糊表述，不要自行补充年份
- 短就是短：源材料只够写一句就写一句，不要为了凑够篇幅重复换说法、不要写空话套话
"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",  # 关闭 deepseek-v4-flash 思维链，避免挤占 content
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Agent Hot News",
            **llm_extra_headers(self.base_url),
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

                required_fields = {"title", "summary", "detail", "category", "sentiment", "entities"}
                if not required_fields.issubset(result.keys()):
                    missing = required_fields - result.keys()
                    raise RuntimeError(f"Missing required fields: {missing}")

                result["category"] = normalize_category(result.get("category"))
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
            "detail": summaries[0][:300] if summaries else "暂无详情",
            "category": "other",
            "sentiment": "neutral",
            "entities": [],
        }
