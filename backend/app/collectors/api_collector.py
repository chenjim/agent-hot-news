import httpx
import json
from datetime import datetime
from typing import List, Any
from app.collectors.base import BaseCollector, RawArticle


class APICollector(BaseCollector):
    """Generic API collector with configurable response parsing via JSONPath-like config."""

    async def fetch(self) -> List[RawArticle]:
        articles = []
        headers = self.extra_config.get("headers", {})
        params = self.extra_config.get("params", {})

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    self.endpoint, headers=headers, params=params
                )
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"API fetch failed for {self.name}: {e}")

        data = response.json()

        # Navigate to the list using config path
        items = data
        list_path = self.extra_config.get("list_path", "")
        if list_path:
            for key in list_path.split("."):
                if key.isdigit():
                    items = items[int(key)]
                else:
                    items = items.get(key, [])

        if not isinstance(items, list):
            items = [items] if items else []

        field_mapping = self.extra_config.get("field_mapping", {})

        for item in items:
            if isinstance(item, dict):
                articles.append(self._parse_item(item, field_mapping))

        return articles

    def _parse_item(self, item: dict, mapping: dict) -> RawArticle:
        def get_field(field_path: str, default: Any = None):
            if not field_path:
                return default
            value = item
            for key in field_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key, default)
                else:
                    return default
            return value

        published = None
        date_str = get_field(mapping.get("published_at", ""))
        if date_str:
            try:
                # Try common formats
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S"]:
                    try:
                        published = datetime.strptime(str(date_str)[:19], fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        return RawArticle(
            url=self._normalize_url(str(get_field(mapping.get("url", ""), ""))),
            title=str(get_field(mapping.get("title", ""), "")),
            summary=str(get_field(mapping.get("summary", ""), ""))[:1000] or None,
            published_at=published,
            source_name=self.name,
            source_url=self.endpoint,
            raw_hot_score=float(get_field(mapping.get("hot_score", ""), 0) or 0),
            language=self.extra_config.get("language", "zh"),
        )
