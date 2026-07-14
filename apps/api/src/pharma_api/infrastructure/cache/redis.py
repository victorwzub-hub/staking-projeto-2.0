from __future__ import annotations

from redis.asyncio import Redis

from pharma_api.core.config import get_settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """Close the cached Redis client without creating one during shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
    _redis_client = None
