"""Embedding 后台 worker：memory / messages / artifacts 异步向量化。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from ..logging import get_logger
from ..recall.messages import (
    fetch_pending_message_ids,
    get_message_embed_text,
    mark_message_embedding_failed,
    mark_message_embedding_skipped,
    write_message_embedding,
)
from .embedder import EmbeddingUnavailable, embed_text
from .store import fetch_pending_ids, get_content, mark_failed, write_embedding

log = get_logger("embed_worker")

EntityKind = Literal["memory", "message", "artifact"]


@dataclass(frozen=True, slots=True)
class _EmbedJob:
    kind: EntityKind
    entity_id: int | str


_queue: asyncio.Queue[_EmbedJob] = asyncio.Queue()
_queued: set[_EmbedJob] = set()
_task: asyncio.Task | None = None
_stop_event = asyncio.Event()


async def enqueue_embedding(memory_id: int, *, bump: bool = False) -> None:
    job = _EmbedJob("memory", memory_id)
    await _enqueue(job, bump=bump)


async def enqueue_message_embedding(message_id: int, *, bump: bool = False) -> None:
    job = _EmbedJob("message", message_id)
    await _enqueue(job, bump=bump)


async def enqueue_artifact_embedding(artifact_id: str, *, bump: bool = False) -> None:
    job = _EmbedJob("artifact", str(artifact_id))
    await _enqueue(job, bump=bump)


async def bump_message_embedding(message_id: int) -> None:
    """内容变更后重置向量并重新入队（合并 update 路径的 reset + enqueue）。"""
    from ..recall.messages import reset_message_embedding

    await reset_message_embedding(message_id)
    await enqueue_message_embedding(message_id, bump=True)


async def _enqueue(job: _EmbedJob, *, bump: bool) -> None:
    if bump:
        _queued.discard(job)
    if job in _queued:
        return
    _queued.add(job)
    await _queue.put(job)


async def _drain_pending() -> None:
    """启动时把 pending 行批量入队。"""
    from ..artifacts.store import fetch_pending_artifact_ids

    pending_memory = await fetch_pending_ids(limit=200)
    pending_messages = await fetch_pending_message_ids(limit=200)
    pending_artifacts = await fetch_pending_artifact_ids(limit=200)
    for mid in pending_memory:
        await enqueue_embedding(mid)
    for msg_id in pending_messages:
        await enqueue_message_embedding(msg_id)
    for aid in pending_artifacts:
        await enqueue_artifact_embedding(aid)
    total = len(pending_memory) + len(pending_messages) + len(pending_artifacts)
    if total:
        log.info(
            "embedding_drain",
            memory=len(pending_memory),
            messages=len(pending_messages),
            artifacts=len(pending_artifacts),
        )


async def _process_job(job: _EmbedJob) -> None:
    retry = False
    requeue_stale = False
    try:
        if job.kind == "memory":
            content = await get_content(int(job.entity_id))
            if content is None:
                return
            try:
                blob = await embed_text(content)
                latest = await get_content(int(job.entity_id))
                if latest != content:
                    requeue_stale = True
                    return
                await write_embedding(int(job.entity_id), blob)
                log.info("embedding_done", kind="memory", id=job.entity_id)
            except EmbeddingUnavailable:
                log.warning("embedding_service_down", kind="memory", id=job.entity_id)
                retry = True
                await asyncio.sleep(5.0)
            except Exception as exc:
                await mark_failed(int(job.entity_id))
                log.error("embedding_failed", kind="memory", id=job.entity_id, error=str(exc))
            return

        if job.kind == "message":
            message_id = int(job.entity_id)
            text = await get_message_embed_text(message_id)
            if text is None:
                await mark_message_embedding_skipped(message_id)
                return
            if not text:
                await mark_message_embedding_skipped(message_id)
                return
            try:
                blob = await embed_text(text)
                latest = await get_message_embed_text(message_id)
                if latest != text:
                    requeue_stale = True
                    return
                await write_message_embedding(message_id, blob)
                log.info("embedding_done", kind="message", id=message_id)
            except EmbeddingUnavailable:
                log.warning("embedding_service_down", kind="message", id=message_id)
                retry = True
                await asyncio.sleep(5.0)
            except Exception as exc:
                await mark_message_embedding_failed(message_id)
                log.error("embedding_failed", kind="message", id=message_id, error=str(exc))
            return

        artifact_id = str(job.entity_id)
        from ..artifacts.store import (
            get_artifact_embed_text,
            mark_artifact_embedding_failed,
            write_artifact_embedding,
        )

        text = await get_artifact_embed_text(artifact_id)
        if not text:
            return
        try:
            blob = await embed_text(text)
            latest = await get_artifact_embed_text(artifact_id)
            if latest != text:
                requeue_stale = True
                return
            await write_artifact_embedding(artifact_id, blob)
            log.info("embedding_done", kind="artifact", id=artifact_id)
        except EmbeddingUnavailable:
            log.warning("embedding_service_down", kind="artifact", id=artifact_id)
            retry = True
            await asyncio.sleep(5.0)
        except Exception as exc:
            await mark_artifact_embedding_failed(artifact_id)
            log.error("embedding_failed", kind="artifact", id=artifact_id, error=str(exc))
    finally:
        if not retry and not requeue_stale:
            _queued.discard(job)

    if retry:
        await _queue.put(job)
    elif requeue_stale:
        await _enqueue(job, bump=True)


async def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            job = await asyncio.wait_for(_queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        await _process_job(job)


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
    _queued.clear()
    log.info("embedding_worker_stopped")
