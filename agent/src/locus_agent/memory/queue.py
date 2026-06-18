"""Embedding 后台 worker：memory / messages / artifacts 异步向量化。

设计要点：
- 优先级：memory > env_var > artifact > message（用户可见项优先）
- 多 worker + embed 信号量：提高吞吐，避免单线程被慢任务拖死
- 启动 bootstrap + 周期性 drain：补齐 DB 中 pending 但未入队的行
- TEI 不可用时非阻塞退避：generation 防 bump/retry 竞态重复入队
- message 入队限流：仅统计活跃队列深度，retry 等待不占 cap
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from ..logging import get_logger
from ..recall.messages import (
    fetch_pending_message_ids,
    get_message_embed_text,
    mark_message_embedding_failed,
    mark_message_embedding_skipped,
    write_message_embedding,
)
from ..workspace import get_workspace_id, iter_workspace_ids, set_workspace_id
from .embedder import EmbeddingUnavailable, embed_text
from .store import (
    fetch_pending_ids,
    get_content,
    mark_failed,
    memory_embedding_state,
    write_embedding,
)

log = get_logger("embed_worker")

EntityKind = Literal["memory", "message", "artifact", "env_var"]

_KIND_PRIORITY: dict[EntityKind, int] = {
    "memory": 0,
    "env_var": 1,
    "artifact": 2,
    "message": 3,
}

_DRAIN_LIMITS: dict[EntityKind, int] = {
    "memory": 100,
    "env_var": 50,
    "artifact": 50,
    "message": 80,
}

_WORKER_COUNT = 2
_EMBED_CONCURRENCY = 2
_MESSAGE_QUEUE_CAP = 120
_RETRY_DELAY_SEC = 5.0
_MAX_RETRY_ATTEMPTS = 12
_DRAIN_INTERVAL_SEC = 15.0

_embed_semaphore = asyncio.Semaphore(_EMBED_CONCURRENCY)
_sequence = 0
_stop_event = asyncio.Event()
_worker_tasks: list[asyncio.Task] = []
_drain_task: asyncio.Task | None = None


@dataclass(frozen=True, slots=True)
class _EmbedJob:
    kind: EntityKind
    entity_id: int | str
    workspace_id: str


_priority_queue: asyncio.PriorityQueue[tuple[int, int, _EmbedJob]] = asyncio.PriorityQueue()
_queued: set[_EmbedJob] = set()
_queued_by_kind: dict[EntityKind, int] = defaultdict(int)
_retry_waiting: set[_EmbedJob] = set()
_job_generation: dict[_EmbedJob, int] = {}
_retry_counts: dict[_EmbedJob, int] = defaultdict(int)


def _job(
    kind: EntityKind,
    entity_id: int | str,
    *,
    workspace_id: str | None = None,
) -> _EmbedJob:
    return _EmbedJob(kind, entity_id, get_workspace_id() if workspace_id is None else workspace_id)


def _pack(job: _EmbedJob) -> tuple[int, int, _EmbedJob]:
    global _sequence
    _sequence += 1
    return (_KIND_PRIORITY[job.kind], _sequence, job)


def _message_backlog() -> int:
    waiting = sum(1 for job in _retry_waiting if job.kind == "message")
    return max(0, _queued_by_kind["message"] - waiting)


def _track_enqueue(job: _EmbedJob) -> None:
    _queued.add(job)
    _queued_by_kind[job.kind] += 1


def _clear_job_state(job: _EmbedJob) -> None:
    _retry_waiting.discard(job)
    _job_generation.pop(job, None)
    _retry_counts.pop(job, None)


def _track_dequeue(job: _EmbedJob) -> None:
    if job in _queued:
        _queued.discard(job)
        _queued_by_kind[job.kind] = max(0, _queued_by_kind[job.kind] - 1)
    _clear_job_state(job)


def _invalidate_retry(job: _EmbedJob) -> None:
    _retry_waiting.discard(job)
    _retry_counts.pop(job, None)
    _job_generation[job] = _job_generation.get(job, 0) + 1


async def enqueue_embedding(
    memory_id: int,
    *,
    bump: bool = False,
    workspace_id: str | None = None,
) -> None:
    await _enqueue(_job("memory", memory_id, workspace_id=workspace_id), bump=bump)


async def enqueue_message_embedding(
    message_id: int,
    *,
    bump: bool = False,
    workspace_id: str | None = None,
) -> None:
    if not bump and _message_backlog() >= _MESSAGE_QUEUE_CAP:
        return
    await _enqueue(_job("message", message_id, workspace_id=workspace_id), bump=bump)


async def enqueue_artifact_embedding(
    artifact_id: str,
    *,
    bump: bool = False,
    workspace_id: str | None = None,
) -> None:
    await _enqueue(_job("artifact", str(artifact_id), workspace_id=workspace_id), bump=bump)


async def enqueue_env_var_embedding(
    env_id: int,
    *,
    bump: bool = False,
    workspace_id: str | None = None,
) -> None:
    await _enqueue(_job("env_var", env_id, workspace_id=workspace_id), bump=bump)


async def bump_message_embedding(message_id: int) -> None:
    from ..recall.messages import reset_message_embedding

    await reset_message_embedding(message_id)
    await enqueue_message_embedding(message_id, bump=True)


async def _enqueue(job: _EmbedJob, *, bump: bool) -> None:
    if bump:
        _invalidate_retry(job)
        _track_dequeue(job)
    if job in _queued:
        return
    _track_enqueue(job)
    _retry_waiting.discard(job)
    await _priority_queue.put(_pack(job))


async def _delayed_requeue(job: _EmbedJob, *, generation: int, delay: float) -> None:
    await asyncio.sleep(delay)
    if _stop_event.is_set():
        _track_dequeue(job)
        return
    if job not in _queued:
        _retry_waiting.discard(job)
        return
    if _job_generation.get(job, 0) != generation:
        _retry_waiting.discard(job)
        return
    _retry_waiting.discard(job)
    await _priority_queue.put(_pack(job))


async def _mark_job_failed(job: _EmbedJob) -> None:
    if job.kind == "memory":
        await mark_failed(int(job.entity_id))
        return
    if job.kind == "message":
        await mark_message_embedding_failed(int(job.entity_id))
        return
    if job.kind == "artifact":
        from ..artifacts.store import mark_artifact_embedding_failed

        await mark_artifact_embedding_failed(str(job.entity_id))
        return
    if job.kind == "env_var":
        from ..env_vars.store import mark_env_var_embedding_failed

        await mark_env_var_embedding_failed(int(job.entity_id))


async def _embed_text_limited(text: str) -> bytes:
    async with _embed_semaphore:
        return await embed_text(text)


async def _finalize_success(job: _EmbedJob) -> None:
    _track_dequeue(job)
    log.info(
        "embedding_done",
        kind=job.kind,
        id=job.entity_id,
        workspace_id=job.workspace_id,
    )


async def _finalize_retry(job: _EmbedJob, *, reason: str) -> None:
    attempt = _retry_counts[job] + 1
    _retry_counts[job] = attempt
    if attempt >= _MAX_RETRY_ATTEMPTS:
        await _mark_job_failed(job)
        _track_dequeue(job)
        log.error(
            "embedding_retry_exhausted",
            kind=job.kind,
            id=job.entity_id,
            workspace_id=job.workspace_id,
            attempts=attempt,
            reason=reason,
        )
        return
    log.warning(
        "embedding_service_down",
        kind=job.kind,
        id=job.entity_id,
        workspace_id=job.workspace_id,
        attempt=attempt,
        reason=reason,
    )
    _retry_waiting.add(job)
    generation = _job_generation.get(job, 0)
    asyncio.create_task(
        _delayed_requeue(job, generation=generation, delay=_RETRY_DELAY_SEC),
        name="embed-retry",
    )


async def _process_memory(job: _EmbedJob) -> None:
    mid = int(job.entity_id)
    content = await get_content(mid)
    if content is None:
        state = await memory_embedding_state(mid)
        if state == "pending":
            await mark_failed(mid)
            log.warning("embedding_memory_missing", id=mid, workspace_id=job.workspace_id)
        else:
            log.debug(
                "embedding_memory_skip_stale",
                id=mid,
                state=state,
                workspace_id=job.workspace_id,
            )
        _track_dequeue(job)
        return
    try:
        blob = await _embed_text_limited(content)
        latest = await get_content(mid)
        if latest != content:
            await _enqueue(job, bump=True)
            return
        await write_embedding(mid, blob)
        await _finalize_success(job)
    except EmbeddingUnavailable as exc:
        await _finalize_retry(job, reason=str(exc))
    except Exception as exc:
        await mark_failed(mid)
        _track_dequeue(job)
        log.error(
            "embedding_failed",
            kind="memory",
            id=mid,
            workspace_id=job.workspace_id,
            error=str(exc),
        )


async def _process_message(job: _EmbedJob) -> None:
    message_id = int(job.entity_id)
    text = await get_message_embed_text(message_id)
    if text is None or not text:
        await mark_message_embedding_skipped(message_id)
        _track_dequeue(job)
        return
    try:
        blob = await _embed_text_limited(text)
        latest = await get_message_embed_text(message_id)
        if latest != text:
            await _enqueue(job, bump=True)
            return
        await write_message_embedding(message_id, blob)
        await _finalize_success(job)
    except EmbeddingUnavailable as exc:
        await _finalize_retry(job, reason=str(exc))
    except Exception as exc:
        await mark_message_embedding_failed(message_id)
        _track_dequeue(job)
        log.error(
            "embedding_failed",
            kind="message",
            id=message_id,
            workspace_id=job.workspace_id,
            error=str(exc),
        )


async def _process_artifact(job: _EmbedJob) -> None:
    from ..artifacts.store import (
        get_artifact_embed_text,
        mark_artifact_embedding_failed,
        write_artifact_embedding,
    )

    artifact_id = str(job.entity_id)
    text = await get_artifact_embed_text(artifact_id)
    if not text:
        await mark_artifact_embedding_failed(artifact_id)
        _track_dequeue(job)
        return
    try:
        blob = await _embed_text_limited(text)
        latest = await get_artifact_embed_text(artifact_id)
        if latest != text:
            await _enqueue(job, bump=True)
            return
        await write_artifact_embedding(artifact_id, blob)
        await _finalize_success(job)
    except EmbeddingUnavailable as exc:
        await _finalize_retry(job, reason=str(exc))
    except Exception as exc:
        await mark_artifact_embedding_failed(artifact_id)
        _track_dequeue(job)
        log.error(
            "embedding_failed",
            kind="artifact",
            id=artifact_id,
            workspace_id=job.workspace_id,
            error=str(exc),
        )


async def _process_env_var(job: _EmbedJob) -> None:
    from ..env_vars.store import (
        env_var_embedding_state,
        get_env_var_embed_text,
        mark_env_var_embedding_failed,
        write_env_var_embedding,
    )

    env_id = int(job.entity_id)
    text = await get_env_var_embed_text(env_id)
    if text is None:
        state = await env_var_embedding_state(env_id)
        if state == "pending":
            await mark_env_var_embedding_failed(env_id)
            log.warning("embedding_env_var_missing", id=env_id, workspace_id=job.workspace_id)
        else:
            log.debug(
                "embedding_env_var_skip_stale",
                id=env_id,
                state=state,
                workspace_id=job.workspace_id,
            )
        _track_dequeue(job)
        return
    if not text.strip():
        await mark_env_var_embedding_failed(env_id)
        _track_dequeue(job)
        return
    try:
        blob = await _embed_text_limited(text)
        latest = await get_env_var_embed_text(env_id)
        if latest != text:
            await _enqueue(job, bump=True)
            return
        await write_env_var_embedding(env_id, blob)
        await _finalize_success(job)
    except EmbeddingUnavailable as exc:
        await _finalize_retry(job, reason=str(exc))
    except Exception as exc:
        await mark_env_var_embedding_failed(env_id)
        _track_dequeue(job)
        log.error(
            "embedding_failed",
            kind="env_var",
            id=env_id,
            workspace_id=job.workspace_id,
            error=str(exc),
        )


_PROCESSORS: dict[EntityKind, Callable[[_EmbedJob], Awaitable[None]]] = {
    "memory": _process_memory,
    "message": _process_message,
    "artifact": _process_artifact,
    "env_var": _process_env_var,
}


async def _process_job(job: _EmbedJob) -> None:
    set_workspace_id(job.workspace_id)
    processor = _PROCESSORS.get(job.kind)
    if processor is None:
        _track_dequeue(job)
        return
    await processor(job)


async def _drain_kind(
    wid: str,
    kind: EntityKind,
    *,
    limit: int,
) -> int:
    set_workspace_id(wid)
    enqueued = 0
    if kind == "memory":
        ids = await fetch_pending_ids(limit=limit)
        for entity_id in ids:
            job = _job("memory", entity_id, workspace_id=wid)
            if job in _queued:
                continue
            await _enqueue(job, bump=False)
            enqueued += 1
        return enqueued
    if kind == "message":
        if _message_backlog() >= _MESSAGE_QUEUE_CAP:
            return 0
        ids = await fetch_pending_message_ids(limit=limit)
        for entity_id in ids:
            job = _job("message", entity_id, workspace_id=wid)
            if job in _queued:
                continue
            await _enqueue(job, bump=False)
            enqueued += 1
            if _message_backlog() >= _MESSAGE_QUEUE_CAP:
                break
        return enqueued
    if kind == "artifact":
        from ..artifacts.store import fetch_pending_artifact_ids

        ids = await fetch_pending_artifact_ids(limit=limit)
        for entity_id in ids:
            job = _job("artifact", entity_id, workspace_id=wid)
            if job in _queued:
                continue
            await _enqueue(job, bump=False)
            enqueued += 1
        return enqueued
    if kind == "env_var":
        from ..env_vars.store import fetch_pending_env_var_ids

        ids = await fetch_pending_env_var_ids(limit=limit)
        for entity_id in ids:
            job = _job("env_var", entity_id, workspace_id=wid)
            if job in _queued:
                continue
            await _enqueue(job, bump=False)
            enqueued += 1
        return enqueued
    return 0


async def _drain_pending_once(*, limits: dict[EntityKind, int] | None = None) -> dict[str, int]:
    """扫描各工作区 pending 行，补齐未入队项。返回本轮各类型入队数。"""
    caps = limits or _DRAIN_LIMITS
    totals = {"memory": 0, "message": 0, "artifact": 0, "env_var": 0}
    for wid in iter_workspace_ids():
        for kind in ("memory", "env_var", "artifact", "message"):
            n = await _drain_kind(wid, kind, limit=caps[kind])
            totals[kind] += n
    total = sum(totals.values())
    if total:
        log.info("embedding_drain", **totals, workspaces=len(iter_workspace_ids()))
    return totals


async def _bootstrap_drain() -> None:
    """启动时优先清空 memory/env_var pending，其余类型拉一轮。"""
    while not _stop_event.is_set():
        memory_n = 0
        env_n = 0
        for wid in iter_workspace_ids():
            memory_n += await _drain_kind(wid, "memory", limit=_DRAIN_LIMITS["memory"])
            env_n += await _drain_kind(wid, "env_var", limit=_DRAIN_LIMITS["env_var"])
        if memory_n == 0 and env_n == 0:
            break
    await _drain_pending_once()


async def _drain_loop() -> None:
    while not _stop_event.is_set():
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=_DRAIN_INTERVAL_SEC)
            return
        except TimeoutError:
            pass
        if _stop_event.is_set():
            return
        try:
            await _drain_pending_once()
        except Exception as exc:
            log.error("embedding_drain_failed", error=str(exc), exc_info=True)


async def _worker_loop(worker_id: int) -> None:
    while not _stop_event.is_set():
        try:
            _priority, _seq, job = await asyncio.wait_for(_priority_queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        try:
            await _process_job(job)
        except Exception as exc:
            _track_dequeue(job)
            log.error(
                "embedding_job_crashed",
                worker=worker_id,
                kind=job.kind,
                id=job.entity_id,
                workspace_id=job.workspace_id,
                error=str(exc),
                exc_info=True,
            )


def _reset_worker_state() -> None:
    _queued.clear()
    _queued_by_kind.clear()
    _retry_waiting.clear()
    _job_generation.clear()
    _retry_counts.clear()


async def start_embedding_worker() -> None:
    global _drain_task, _worker_tasks
    if _worker_tasks and any(not t.done() for t in _worker_tasks):
        return
    _stop_event.clear()
    _reset_worker_state()
    await _bootstrap_drain()
    _drain_task = asyncio.create_task(_drain_loop(), name="embedding-drain")
    _worker_tasks = [
        asyncio.create_task(_worker_loop(i), name=f"embedding-worker-{i}")
        for i in range(_WORKER_COUNT)
    ]
    log.info(
        "embedding_worker_started",
        workers=_WORKER_COUNT,
        embed_concurrency=_EMBED_CONCURRENCY,
    )


def get_embedding_queue_stats(*, workspace_id: str | None = None) -> dict[str, int | dict[str, int]]:
    """返回内存队列深度；可按工作区过滤。"""

    def matches(job: _EmbedJob) -> bool:
        return workspace_id is None or job.workspace_id == workspace_id

    by_kind: dict[str, int] = defaultdict(int)
    queued = 0
    retry_waiting = 0
    for job in _queued:
        if not matches(job):
            continue
        queued += 1
        by_kind[job.kind] += 1
    for job in _retry_waiting:
        if matches(job):
            retry_waiting += 1
    return {
        "queued": queued,
        "retry_waiting": retry_waiting,
        "by_kind": dict(by_kind),
    }


async def stop_embedding_worker() -> None:
    global _drain_task, _worker_tasks
    _stop_event.set()
    if _drain_task is not None:
        _drain_task.cancel()
        await asyncio.gather(_drain_task, return_exceptions=True)
        _drain_task = None
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        _worker_tasks = []
    _reset_worker_state()
    while not _priority_queue.empty():
        try:
            _priority_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    log.info("embedding_worker_stopped")
