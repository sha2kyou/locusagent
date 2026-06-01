"""Redis client lifecycle for host services."""

from __future__ import annotations

import inspect

import redis.asyncio as redis

from .config import get_settings

_redis_client: redis.Redis | None = None


async def init_redis() -> None:
    global _redis_client
    settings = get_settings()
    redis_url = settings.redis_url.strip()
    if not redis_url:
        raise RuntimeError("REDIS_URL is required")
    client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    await client.ping()
    _redis_client = client


def get_redis() -> redis.Redis:
    if _redis_client is None:
        raise RuntimeError("redis client is not initialized")
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    client = _redis_client
    _redis_client = None
    if client is None:
        return
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(client, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result
