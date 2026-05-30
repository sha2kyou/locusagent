"""周期性后台任务：空闲暂停 / 暂停后停止 / 孤儿资源回收。

调度策略（避免引入 APScheduler 等依赖）：单 asyncio Task 循环，间隔 60s。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..config import get_settings
from ..db import ContainerStatus, User, get_session
from ..logging import get_logger
from .cleanup import run_orphan_cleanup_once
from .lifecycle import pause_container, stop_container

log = get_logger("jobs")

SCAN_INTERVAL = 60.0


async def _scan_once() -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    pause_threshold = now - timedelta(seconds=settings.idle_pause_seconds)
    stop_threshold = now - timedelta(seconds=settings.pause_to_stop_seconds)

    async with get_session() as session:
        rows = (
            await session.execute(
                select(User).where(
                    User.deleted_at.is_(None),
                    User.container_status.in_(
                        [ContainerStatus.RUNNING.value, ContainerStatus.PAUSED.value]
                    ),
                )
            )
        ).scalars().all()

    for user in rows:
        last = user.last_active
        if last is None:
            continue
        try:
            if user.container_status == ContainerStatus.RUNNING.value and last < pause_threshold:
                log.info("auto_pausing", user_id=user.id, last_active=str(last))
                await pause_container(user.id)
            elif user.container_status == ContainerStatus.PAUSED.value and last < stop_threshold:
                log.info("auto_stopping", user_id=user.id, last_active=str(last))
                await stop_container(user.id)
        except Exception as exc:
            log.warning("lifecycle_job_failed", user_id=user.id, error=str(exc))

    try:
        await run_orphan_cleanup_once()
    except Exception as exc:
        log.warning("orphan_cleanup_scan_failed", error=str(exc))

    try:
        from ..scheduled_tasks.executor import schedule_due_task_scan

        schedule_due_task_scan()
    except Exception as exc:
        log.warning("scheduled_tasks_scan_failed", error=str(exc))


async def lifecycle_loop(stop_event: asyncio.Event) -> None:
    log.info("lifecycle_loop_started", interval=SCAN_INTERVAL)
    while not stop_event.is_set():
        try:
            await _scan_once()
        except Exception as exc:
            log.error("lifecycle_scan_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SCAN_INTERVAL)
        except TimeoutError:
            continue
    log.info("lifecycle_loop_stopped")
