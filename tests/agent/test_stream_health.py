"""流式健康检查单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from agentpod_agent.core.stream_health import StreamHealthError, iter_with_stream_health


async def _slow_stream(delay_s: float, items: list[str]):
    for item in items:
        await asyncio.sleep(delay_s)
        yield item


@pytest.mark.asyncio
async def test_iter_passes_through_fast_stream() -> None:
    async def gen():
        yield "a"
        yield "b"

    out = [x async for x in iter_with_stream_health(gen(), chunk_timeout_s=5.0)]
    assert out == ["a", "b"]


@pytest.mark.asyncio
async def test_chunk_stale_raises() -> None:
    stream = _slow_stream(0.15, ["only"])
    with pytest.raises(StreamHealthError) as exc:
        async for _ in iter_with_stream_health(stream, chunk_timeout_s=0.05):
            pass
    assert exc.value.code == "stream_stale"


@pytest.mark.asyncio
async def test_total_duration_raises() -> None:
    stream = _slow_stream(0.05, ["a", "b", "c"])
    with pytest.raises(StreamHealthError) as exc:
        async for _ in iter_with_stream_health(
            stream,
            chunk_timeout_s=10.0,
            max_total_s=0.12,
        ):
            pass
    assert exc.value.code == "stream_total_timeout"
