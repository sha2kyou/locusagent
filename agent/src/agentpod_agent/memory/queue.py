"""Embedding 后台 worker：从 pending 队列拉取并生成向量。

不阻塞写入：写入 add_memory 即返回，向量异步追加。
"""

from __future__ import annotations

import asyncio

from ..logging import get_logger
from .embedder import EmbeddingUnavailable, embed_text
from .store import fetch_pending_ids, get_content, mark_failed, write_embedding

log = get_logger("embed_worker")

_queue: asyncio.Queue[int] = asyncio.Queue()
_task: asyncio.Task | None = None
_stop_event = asyncio.Event()


async def enqueue_embedding(memory_id: int) -> None:
    await _queue.put(memory_id)


async def _drain_pending() -> None:
    """启动时把 pending 行批量入队。"""
    pending = await fetch_pending_ids(limit=200)
    for mid in pending:
        await _queue.put(mid)
    if pending:
        log.info("embedding_drain", count=len(pending))


async def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            mid = await asyncio.wait_for(_queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        content = await get_content(mid)
        if content is None:
            continue
        try:
            blob = await embed_text(content)
            await write_embedding(mid, blob)
            log.info("embedding_done", id=mid)
        except EmbeddingUnavailable:
            await mark_failed(mid)
            log.warning("embedding_service_down", id=mid)
            await asyncio.sleep(5.0)
        except Exception as exc:
            await mark_failed(mid)
            log.error("embedding_failed", id=mid, error=str(exc))


async def start_embedding_worker() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _stop_event.clear()
    await _drain_pending()
    _task = asyncio.create_task(_worker_loop(), name="embedding-worker")
    log.info("embedding_worker_started")


async def stop_embedding_worker() -> None:
    global _task
    _stop_event.set()
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=2.0)
        except TimeoutError:
            _task.cancel()
    _task = None
    log.info("embedding_worker_stopped")
