import redis.asyncio as redis
from app.core.config import get_settings
from loguru import logger

_aredis: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Return a shared async Redis client instance."""
    global _aredis
    if _aredis is None:
        settings = get_settings()
        _aredis = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        logger.info(f"Redis client initialized: {settings.REDIS_URL}")
    return _aredis


async def close_redis_client():
    """Close the shared Redis client connection."""
    global _aredis
    if _aredis is not None:
        await _aredis.close()
        _aredis = None
        logger.info("Redis client closed")
