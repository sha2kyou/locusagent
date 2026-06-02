"""流式 LLM 响应健康检查：单 chunk 空闲超时与整段时长上限。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import TypeVar

T = TypeVar("T")


class StreamHealthError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def iter_with_stream_health(
    stream: AsyncIterator[T],
    *,
    chunk_timeout_s: float,
    max_total_s: float | None = None,
) -> AsyncIterator[T]:
    """包装流式迭代：过久无 chunk 或总时长超限则抛出 StreamHealthError。"""
    if chunk_timeout_s <= 0 and (max_total_s is None or max_total_s <= 0):
        async for item in stream:
            yield item
        return

    started = time.monotonic()
    iterator = stream.__aiter__()
    while True:
        now = time.monotonic()
        if max_total_s is not None and max_total_s > 0 and now - started > max_total_s:
            raise StreamHealthError(
                "stream_total_timeout",
                f"流式响应总时长超过 {int(max_total_s)} 秒，已中止等待。",
            )
        wait_s = chunk_timeout_s if chunk_timeout_s > 0 else None
        try:
            if wait_s is None:
                item = await iterator.__anext__()
            else:
                item = await asyncio.wait_for(iterator.__anext__(), timeout=wait_s)
        except StopAsyncIteration:
            break
        except TimeoutError as exc:
            raise StreamHealthError(
                "stream_stale",
                f"流式响应已超过 {int(chunk_timeout_s)} 秒无新数据，可能上游挂起或网络中断。",
            ) from exc
        yield item
