"""任务完成后的后台增强：Background Self-Improvement Review + 记忆策展。

均为后台任务，失败安全（仅记录日志，不影响主响应）。
通过单 worker 队列串行执行，避免多路 LLM 审查/策展与前台争用线程池与 SQLite。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..logging import get_logger
from .background_review import assess_background_review_triggers, run_background_review
from .persistence import build_llm_messages

log = get_logger("post_run")

_POST_RUN_QUEUE_MAX = 16
_post_run_queue: asyncio.Queue[_PostRunJob] | None = None
_post_run_worker: asyncio.Task[None] | None = None
_post_run_worker_lock = asyncio.Lock()


@dataclass(slots=True)
class _PostRunJob:
    session_id: str
    loop_rounds: int
    model: str | None
    messages: list[dict[str, Any]] | None
    done: asyncio.Future[None] | None = None


async def _execute_post_tasks(job: _PostRunJob) -> None:
    trajectory = job.messages if job.messages is not None else await build_llm_messages(job.session_id)

    try:
        from .session_title import finalize_session_title

        await finalize_session_title(job.session_id, messages=trajectory)
    except Exception as exc:
        log.warning("post_run_session_title_failed", error=str(exc))

    try:
        if trajectory:
            review_memory, review_skills = await assess_background_review_triggers(
                session_id=job.session_id,
                loop_rounds=job.loop_rounds,
            )
            if review_memory or review_skills:
                await run_background_review(
                    trajectory,
                    review_memory=review_memory,
                    review_skills=review_skills,
                    model=job.model,
                    session_id=job.session_id,
                )
    except Exception as exc:
        log.warning("post_run_background_review_failed", error=str(exc))

    try:
        from ..memory import maybe_curate_memories

        await maybe_curate_memories(model=job.model)
    except Exception as exc:
        log.warning("post_run_curate_failed", error=str(exc))


async def _post_run_worker_loop() -> None:
    assert _post_run_queue is not None
    while True:
        job = await _post_run_queue.get()
        try:
            await _execute_post_tasks(job)
        except asyncio.CancelledError:
            if job.done is not None and not job.done.done():
                job.done.cancel()
            raise
        except Exception as exc:
            log.warning(
                "post_run_worker_failed",
                session_id=job.session_id,
                error=str(exc),
            )
            if job.done is not None and not job.done.done():
                job.done.set_exception(exc)
        else:
            if job.done is not None and not job.done.done():
                job.done.set_result(None)
        finally:
            _post_run_queue.task_done()


async def _ensure_post_run_worker() -> asyncio.Queue[_PostRunJob]:
    global _post_run_queue, _post_run_worker
    async with _post_run_worker_lock:
        if _post_run_queue is None:
            _post_run_queue = asyncio.Queue(maxsize=_POST_RUN_QUEUE_MAX)
        if _post_run_worker is None or _post_run_worker.done():
            _post_run_worker = asyncio.create_task(_post_run_worker_loop(), name="post-run-worker")
        return _post_run_queue


def schedule_post_run(
    *,
    session_id: str,
    loop_rounds: int = 0,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    """将 post-run 任务入队；队列满时丢弃并记录日志，不阻塞调用方。"""
    async def _enqueue() -> None:
        queue = await _ensure_post_run_worker()
        job = _PostRunJob(
            session_id=session_id,
            loop_rounds=loop_rounds,
            model=model,
            messages=messages,
        )
        try:
            queue.put_nowait(job)
        except asyncio.QueueFull:
            log.warning("post_run_queue_full", session_id=session_id, maxsize=_POST_RUN_QUEUE_MAX)

    asyncio.create_task(_enqueue(), name=f"post-run-enqueue-{session_id}")


async def run_post_tasks(
    *,
    session_id: str,
    loop_rounds: int = 0,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    """兼容旧调用：入队并等待该任务完成。"""
    queue = await _ensure_post_run_worker()
    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    job = _PostRunJob(
        session_id=session_id,
        loop_rounds=loop_rounds,
        model=model,
        messages=messages,
        done=done,
    )
    await queue.put(job)
    await done


async def shutdown_post_run_worker(*, timeout_seconds: float = 3.0) -> None:
    global _post_run_queue, _post_run_worker
    worker = _post_run_worker
    queue = _post_run_queue
    if worker is None or worker.done():
        _post_run_worker = None
        _post_run_queue = None
        return
    worker.cancel()
    try:
        await asyncio.wait_for(worker, timeout=timeout_seconds)
    except (TimeoutError, asyncio.CancelledError):
        pass
    _post_run_worker = None
    if queue is not None:
        while not queue.empty():
            try:
                queue.get_nowait()
                queue.task_done()
            except asyncio.QueueEmpty:
                break
    _post_run_queue = None
