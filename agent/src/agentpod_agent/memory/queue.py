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


@dataclass(frozen=True, slots=True)
class _EmbedJob:
    kind: EntityKind
    entity_id: int | str
    workspace_id: str


_queue: asyncio.Queue[_EmbedJob] = asyncio.Queue()
_queued: set[_EmbedJob] = set()
_task: asyncio.Task | None = None
_stop_event = asyncio.Event()


def _job(
    kind: EntityKind,
    entity_id: int | str,
    *,
    workspace_id: str | None = None,
) -> _EmbedJob:
    return _EmbedJob(kind, entity_id, get_workspace_id() if workspace_id is None else workspace_id)


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
    """启动时扫描各工作区，把 pending 行批量入队。"""
    from ..artifacts.store import fetch_pending_artifact_ids

    from ..env_vars.store import fetch_pending_env_var_ids

    total_memory = 0
    total_messages = 0
    total_artifacts = 0
    total_env_vars = 0
    workspace_count = len(iter_workspace_ids())
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        pending_memory = await fetch_pending_ids(limit=200)
        pending_messages = await fetch_pending_message_ids(limit=200)
        pending_artifacts = await fetch_pending_artifact_ids(limit=200)
        pending_env_vars = await fetch_pending_env_var_ids(limit=200)
        for mid in pending_memory:
            await enqueue_embedding(mid, workspace_id=wid)
        for msg_id in pending_messages:
            await enqueue_message_embedding(msg_id, workspace_id=wid)
        for aid in pending_artifacts:
            await enqueue_artifact_embedding(aid, workspace_id=wid)
        for eid in pending_env_vars:
            await enqueue_env_var_embedding(eid, workspace_id=wid)
        total_memory += len(pending_memory)
        total_messages += len(pending_messages)
        total_artifacts += len(pending_artifacts)
        total_env_vars += len(pending_env_vars)
    total = total_memory + total_messages + total_artifacts + total_env_vars
    if total:
        log.info(
            "embedding_drain",
            memory=total_memory,
            messages=total_messages,
            artifacts=total_artifacts,
            env_vars=total_env_vars,
            workspaces=workspace_count,
        )


async def _process_job(job: _EmbedJob) -> None:
    set_workspace_id(job.workspace_id)
    retry = False
    requeue_stale = False
    try:
        if job.kind == "memory":
            content = await get_content(int(job.entity_id))
            if content is None:
                mid = int(job.entity_id)
                state = await memory_embedding_state(mid)
                if state == "pending":
                    await mark_failed(mid)
                    log.warning(
                        "embedding_memory_missing",
                        id=mid,
                        workspace_id=job.workspace_id,
                    )
                else:
                    log.debug(
                        "embedding_memory_skip_stale",
                        id=mid,
                        state=state,
                        workspace_id=job.workspace_id,
                    )
                return
            try:
                blob = await embed_text(content)
                latest = await get_content(int(job.entity_id))
                if latest != content:
                    requeue_stale = True
                    return
                await write_embedding(int(job.entity_id), blob)
                log.info(
                    "embedding_done",
                    kind="memory",
                    id=job.entity_id,
                    workspace_id=job.workspace_id,
                )
            except EmbeddingUnavailable:
                log.warning(
                    "embedding_service_down",
                    kind="memory",
                    id=job.entity_id,
                    workspace_id=job.workspace_id,
                )
                retry = True
                await asyncio.sleep(5.0)
            except Exception as exc:
                await mark_failed(int(job.entity_id))
                log.error(
                    "embedding_failed",
                    kind="memory",
                    id=job.entity_id,
                    workspace_id=job.workspace_id,
                    error=str(exc),
                )
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
                log.info(
                    "embedding_done",
                    kind="message",
                    id=message_id,
                    workspace_id=job.workspace_id,
                )
            except EmbeddingUnavailable:
                log.warning(
                    "embedding_service_down",
                    kind="message",
                    id=message_id,
                    workspace_id=job.workspace_id,
                )
                retry = True
                await asyncio.sleep(5.0)
            except Exception as exc:
                await mark_message_embedding_failed(message_id)
                log.error(
                    "embedding_failed",
                    kind="message",
                    id=message_id,
                    workspace_id=job.workspace_id,
                    error=str(exc),
                )
            return

        if job.kind == "artifact":
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
                log.info(
                    "embedding_done",
                    kind="artifact",
                    id=artifact_id,
                    workspace_id=job.workspace_id,
                )
            except EmbeddingUnavailable:
                log.warning(
                    "embedding_service_down",
                    kind="artifact",
                    id=artifact_id,
                    workspace_id=job.workspace_id,
                )
                retry = True
                await asyncio.sleep(5.0)
            except Exception as exc:
                await mark_artifact_embedding_failed(artifact_id)
                log.error(
                    "embedding_failed",
                    kind="artifact",
                    id=artifact_id,
                    workspace_id=job.workspace_id,
                    error=str(exc),
                )
            return

        if job.kind == "env_var":
            from ..env_vars.store import (
                get_env_var_embed_text,
                mark_env_var_embedding_failed,
                write_env_var_embedding,
            )

            env_id = int(job.entity_id)
            text = await get_env_var_embed_text(env_id)
            if text is None:
                from ..env_vars.store import env_var_embedding_state

                state = await env_var_embedding_state(env_id)
                if state == "pending":
                    await mark_env_var_embedding_failed(env_id)
                    log.warning(
                        "embedding_env_var_missing",
                        id=env_id,
                        workspace_id=job.workspace_id,
                    )
                else:
                    log.debug(
                        "embedding_env_var_skip_stale",
                        id=env_id,
                        state=state,
                        workspace_id=job.workspace_id,
                    )
                return
            if not text.strip():
                await mark_env_var_embedding_failed(env_id)
                return
            try:
                blob = await embed_text(text)
                latest = await get_env_var_embed_text(env_id)
                if latest != text:
                    requeue_stale = True
                    return
                await write_env_var_embedding(env_id, blob)
                log.info(
                    "embedding_done",
                    kind="env_var",
                    id=env_id,
                    workspace_id=job.workspace_id,
                )
            except EmbeddingUnavailable:
                log.warning(
                    "embedding_service_down",
                    kind="env_var",
                    id=env_id,
                    workspace_id=job.workspace_id,
                )
                retry = True
                await asyncio.sleep(5.0)
            except Exception as exc:
                await mark_env_var_embedding_failed(env_id)
                log.error(
                    "embedding_failed",
                    kind="env_var",
                    id=env_id,
                    workspace_id=job.workspace_id,
                    error=str(exc),
                )
            return

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
            await asyncio.gather(_task, return_exceptions=True)
    _task = None
    _queued.clear()
    log.info("embedding_worker_stopped")
