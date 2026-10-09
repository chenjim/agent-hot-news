"""LLM 事件归属判定（方案 B）。

职责分离：
  - 向量只负责**召回**（给每个待归类条目挑最像的 K 个候选事件，宁宽勿严）
  - LLM 负责**判定**（这些候选里有没有它真正报道的那个事件）

之所以不继续用向量阈值判定：同事件的两簇质心实测可低到 0.58，
不同事件实测可高到 0.89，两类分布重叠，任何全局阈值必然同时
漏并和误并。LLM 读的是两条标题的字面语义，能分辨"同一场比赛"
和"同一运动员的不同传闻"。

失败语义：任何一步出错都返回 None（而不是"全部判新"），
调用方据此退回旧的向量阈值路径，不让归属判定故障拖垮整条流水线。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import httpx
from loguru import logger

from app.core.config import get_settings, llm_extra_headers

settings = get_settings()

# key -> [(event_id, event_title), ...]，按相似度降序，已过滤召回下限
CandidateMap = Mapping[str, Sequence[Tuple[int, str]]]


@dataclass(frozen=True)
class RouteItem:
    """一个待归类条目：一个 DBSCAN 簇，或一篇 outlier 文章。"""

    key: str
    title: str
    summary: str = ""


@dataclass(frozen=True)
class RouteDecision:
    key: str
    event_id: Optional[int]  # None = 归为新事件


_SYSTEM = (
    "你是新闻事件归类助手。给定一批待归类条目，每条后面附有它的候选已有事件。"
    "判断该条目报道的是不是候选中的某一个事件。只输出合法 JSON，"
    "不要输出推理过程、解释或 Markdown。"
)

_USER_TEMPLATE = """以下是待归类条目，方括号内是条目编号，"候选"后面是该条目向量召回出的已有事件（编号=事件标题）：

{items}

请严格输出以下 JSON，不要添加任何其他内容：
{{"decisions":[{{"i":0,"event_id":123}},{{"i":1,"event_id":null}}]}}

要求：
1. 每个条目编号必须恰好出现一次，顺序不限
2. event_id 只能填该条目"候选"里列出的编号；若该条目不属于任何候选事件，填 null
3. 只有报道**同一个具体事件**时才归属。主题相关但属于不同事件的必须填 null，
   例如：同一运动员的不同场次、同一人的不同传闻、同一公司的不同产品、
   同一话题的不同角度报道
4. 宁可填 null 也不要勉强归属：填错会造成两个不同事件被合并，比多出一个重复事件更难修复
"""


class EventRouter:
    def __init__(self) -> None:
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self.model = settings.OPENAI_CHAT_MODEL
        self._sem = asyncio.Semaphore(2)
        self._last_call = 0.0

    async def _wait_if_needed(self) -> None:
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_call
        if elapsed < 3.0:
            await asyncio.sleep(3.0 - elapsed)
        self._last_call = loop.time()

    # ------------------------------------------------------------------
    # prompt
    # ------------------------------------------------------------------
    @staticmethod
    def _format_items(
        items: Sequence[RouteItem], candidates: CandidateMap
    ) -> str:
        blocks = []
        for idx, item in enumerate(items):
            title = (item.title or "").strip()[:200]
            summary = (item.summary or "").strip()
            head = f"[{idx}] {title}"
            if summary and summary != title:
                head += f"\n    概要: {summary[:200]}"
            cands = candidates.get(item.key) or []
            if cands:
                rendered = " | ".join(f"{eid}={etitle}" for eid, etitle in cands)
                head += f"\n    候选: {rendered[:1200]}"
            else:
                head += "\n    候选: （无）"
            blocks.append(head)
        return "\n".join(blocks)

    @staticmethod
    def _parse(raw: str) -> dict:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]
        return json.loads(text)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
    async def route(
        self,
        items: Sequence[RouteItem],
        candidates: CandidateMap,
    ) -> Optional[List[RouteDecision]]:
        """判定每个条目的归属。

        返回按 items 顺序的完整判定列表；LLM 或解析失败时返回 None，
        调用方应回退到旧路径。无候选的条目不进 LLM，直接判"新事件"。
        """
        if not items:
            return []

        decodable = [it for i, it in enumerate(items) if candidates.get(it.key)]
        if not decodable:
            logger.info("Router: no item has a candidate above recall floor, all new")
            return [
                RouteDecision(key=it.key, event_id=None) for it in items
            ]

        by_key: Dict[str, Optional[int]] = {}
        for start in range(0, len(decodable), settings.ROUTE_BATCH_SIZE):
            chunk = decodable[start : start + settings.ROUTE_BATCH_SIZE]
            got = await self._route_chunk(chunk, candidates)
            if got is None:
                return None
            by_key.update(got)

        return [
            RouteDecision(key=it.key, event_id=by_key.get(it.key))
            for it in items
        ]

    async def _route_chunk(
        self,
        chunk: Sequence[RouteItem],
        candidates: CandidateMap,
    ) -> Optional[Dict[str, Optional[int]]]:
        prompt = _USER_TEMPLATE.format(
            items=self._format_items(chunk, candidates)
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Agent Hot News",
            **llm_extra_headers(self.base_url),
        }

        raw: Optional[str] = None
        for attempt in range(3):
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
                    logger.warning(
                        f"Router rate limited (429), waiting {retry_after}s..."
                    )
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError("API returned no choices")
                raw = choices[0]["message"]["content"].strip()
                if raw:
                    break
                raw = None
            except Exception as exc:  # noqa: BLE001 - 统一按失败回退
                logger.warning(f"Router LLM call failed (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(2 * (attempt + 1))
        else:
            raw = None

        if not raw:
            return None

        try:
            parsed = self._parse(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Router failed to parse LLM output: {exc}")
            return None

        raw_decisions = parsed.get("decisions")
        if not isinstance(raw_decisions, list):
            logger.warning("Router: LLM output has no 'decisions' list")
            return None

        # key -> 该条目允许的候选 id 集合，用于把 LLM 幻觉出的 id 挡回去
        allowed: Dict[str, set] = {
            it.key: {eid for eid, _ in (candidates.get(it.key) or [])}
            for it in chunk
        }
        index_by_pos: Dict[int, RouteItem] = {i: it for i, it in enumerate(chunk)}

        out: Dict[str, Optional[int]] = {it.key: None for it in chunk}
        for entry in raw_decisions:
            if not isinstance(entry, dict):
                continue
            pos = entry.get("i")
            if not isinstance(pos, int) or pos not in index_by_pos:
                continue
            item = index_by_pos[pos]
            eid = entry.get("event_id")
            if eid is None:
                continue
            if isinstance(eid, str) and eid.isdigit():
                eid = int(eid)
            if not isinstance(eid, int):
                logger.warning(f"Router: bad event_id {eid!r} for {item.key}")
                continue
            if eid in allowed[item.key]:
                out[item.key] = eid
            else:
                # 不在该条目的召回集合里：要么是幻觉，要么是模型串行了条目
                logger.warning(
                    f"Router: event_id {eid} not in candidates of {item.key}, dropped"
                )
        return out
