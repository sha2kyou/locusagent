"""进程内 TTL 缓存，替代 Redis。"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from typing import Any

_cache: dict[str, tuple[str, float | None]] = {}
_lock = asyncio.Lock()

_rate_windows: dict[str, list[float]] = defaultdict(list)
_rate_lock = asyncio.Lock()


async def cache_get(key: str) -> str | None:
    async with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() >= expires_at:
            _cache.pop(key, None)
            return None
        return value


async def cache_set(key: str, value: str, *, ex: int | None = None) -> None:
    expires_at = time.time() + ex if ex else None
    async with _lock:
        _cache[key] = (value, expires_at)


async def cache_delete(key: str) -> None:
    async with _lock:
        _cache.pop(key, None)


class MemoryCache:
    """与 Redis asyncio 客户端兼容的最小接口。"""

    async def get(self, key: str) -> str | None:
        return await cache_get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        await cache_set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await cache_delete(key)


_client: MemoryCache | None = None


async def init_cache() -> None:
    global _client
    _client = MemoryCache()


def get_cache() -> MemoryCache:
    if _client is None:
        raise RuntimeError("memory cache is not initialized")
    return _client


async def close_cache() -> None:
    global _client
    _client = None
    async with _lock:
        _cache.clear()
    async with _rate_lock:
        _rate_windows.clear()


async def enforce_sliding_rate_limit(
    *,
    bucket: str,
    workspace_id: str | None,
    limit: int,
    window_seconds: float = 60.0,
) -> bool:
    """返回 True 表示允许，False 表示超限。"""
    if limit <= 0:
        return True
    ws = (workspace_id or "").strip()
    key = f"{bucket}:ws:{ws}" if ws else bucket
    now = time.time()
    async with _rate_lock:
        window = [t for t in _rate_windows[key] if now - t < window_seconds]
        if len(window) >= limit:
            _rate_windows[key] = window
            return False
        window.append(now)
        _rate_windows[key] = window
        return True


def new_rate_member() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex}"
