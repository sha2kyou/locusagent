"""进程内缓存生命周期。"""

from __future__ import annotations

from locus_shared.memory_cache import close_cache, get_cache, init_cache


async def init_app_cache() -> None:
    await init_cache()


def get_app_cache():
    return get_cache()


async def close_app_cache() -> None:
    await close_cache()
