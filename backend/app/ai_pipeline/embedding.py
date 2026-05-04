from typing import List, Optional
import numpy as np
import httpx
from app.core.config import get_settings
from loguru import logger

settings = get_settings()


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
        batch_size = 10

        async with httpx.AsyncClient(timeout=60.0) as client:
            for batch_start in range(0, total, batch_size):
                batch_end = batch_start + batch_size
                batch = cleaned[batch_start:batch_end]
                logger.info(f"Embedding batch {batch_start + 1}-{min(batch_end, total)}/{total}...")

                payload = {
                    "model": self.model,
                    "input": batch,
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://localhost",
                    "X-Title": "Agent Hot News",
                }

                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                if not data.get("data"):
                    raise RuntimeError(f"API returned empty data: {data}")

                # Sort by index to ensure correct order
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                for item in sorted_data:
                    all_embeddings.append(item["embedding"])

        logger.info(f"Embedded {len(all_embeddings)} texts with {self.model}")
        return all_embeddings

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))
