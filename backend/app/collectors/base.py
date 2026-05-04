from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class RawArticle:
    url: str
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[datetime] = None
    source_name: str = ""
    source_url: Optional[str] = None
    raw_hot_score: float = 0.0
    language: str = "zh"
    extra: Optional[Dict[str, Any]] = None


class BaseCollector(ABC):
    def __init__(self, source_config: Dict[str, Any]):
        self.config = source_config
        self.name = source_config.get("name", "unknown")
        self.endpoint = source_config.get("endpoint", "")
        self.extra_config = source_config.get("config", {})

    @abstractmethod
    async def fetch(self) -> List[RawArticle]:
        """Fetch articles from the source. Must be implemented by subclasses."""
        pass

    def _normalize_url(self, url: str) -> str:
        """Basic URL normalization to help deduplication."""
        return url.strip().split("?")[0].rstrip("/")
