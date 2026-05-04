import json
import hashlib
import functools
from typing import Any, Callable

from fastapi import Request
from loguru import logger

from app.cache.redis_client import get_redis_client


def _generate_cache_key(func_name: str, *args, **kwargs) -> str:
    """Generate a deterministic cache key from arguments."""
    serializable = []
    for arg in args:
        if isinstance(arg, (str, int, float, bool, list, dict, tuple)):
            serializable.append(arg)
        elif isinstance(arg, Request):
            serializable.append({"path": arg.url.path, "query": str(arg.query_params)})

    for k, v in kwargs.items():
        if isinstance(v, (str, int, float, bool, list, dict, tuple)):
            serializable.append({k: v})

    raw = json.dumps(serializable, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"cache:{func_name}:{digest}"


def _default_json(obj: Any) -> Any:
    """JSON default serializer supporting Pydantic and SQLAlchemy models."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__table__"):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return str(obj)


def cache_response(ttl: int = 60):
    """Decorator to cache FastAPI endpoint responses in Redis.

    Args:
        ttl: Time-to-live in seconds.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            redis_client = get_redis_client()
            cache_key = _generate_cache_key(func.__qualname__, *args, **kwargs)

            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")

            result = await func(*args, **kwargs)

            try:
                serialized = json.dumps(result, default=_default_json)
                await redis_client.setex(cache_key, ttl, serialized)
                logger.debug(f"Cache set: {cache_key} (ttl={ttl}s)")
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

            return result

        return async_wrapper
    return decorator
