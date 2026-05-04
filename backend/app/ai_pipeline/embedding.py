import asyncio
from typing import List, Optional
import numpy as np
import httpx
from app.core.config import get_settings
from loguru import logger

settings = get_settings()

BATCH_SIZE = 10
BATCH_INTERVAL = 2.0  # seconds between batches to avoid rate limits


class EmbeddingService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self.model = settings.OPENAI_EMBEDDING_MODEL

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""
        if not texts:
            return []

        cleaned = [t.strip()[:4000] for t in texts if t.strip()]
        if not cleaned:
            return []

        all_embeddings = []
        total = len(cleaned)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Agent Hot News",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            for batch_start in range(0, total, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total)
                batch = cleaned[batch_start:batch_end]
                logger.info(f"Embedding batch {batch_start + 1}-{batch_end}/{total}...")

                payload = {"model": self.model, "input": batch}

                for attempt in range(3):
                    resp = await client.post(
                        f"{self.base_url}/embeddings",
                        headers=headers,
                        json=payload,
                    )

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        logger.warning(f"Embedding rate limited (429), waiting {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()
                    break
                else:
                    raise RuntimeError(f"Embedding batch {batch_start} failed after 3 retries")

                data = resp.json()
                if not data.get("data"):
                    raise RuntimeError(f"API returned empty data: {data}")

                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                for item in sorted_data:
                    all_embeddings.append(item["embedding"])

                # Wait between batches to avoid rate limits
                if batch_end < total:
                    await asyncio.sleep(BATCH_INTERVAL)

        logger.info(f"Embedded {len(all_embeddings)} texts with {self.model}")
        return all_embeddings

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))
