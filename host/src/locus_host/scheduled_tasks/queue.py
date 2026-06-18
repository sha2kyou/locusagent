"""Asyncio scheduled task scanner: every 30s run due tasks."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from ..logging import get_logger

log = get_logger("scheduled_queue")
_SCAN_INTERVAL_SECONDS = 30.0
_WORKER_TASK_NAME = "scheduled-task-worker"


async def _scan_loop() -> None:
    from .executor import scan_and_run_due_tasks

    while True:
        try:
            await scan_and_run_due_tasks()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("scheduled_task_scan_failed", error=str(exc))
        await asyncio.sleep(_SCAN_INTERVAL_SECONDS)


@asynccontextmanager
async def scheduled_task_worker_context():
    worker = asyncio.create_task(_scan_loop(), name=_WORKER_TASK_NAME)
    log.info("scheduled_task_worker_started")
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        log.info("scheduled_task_worker_stopped")
