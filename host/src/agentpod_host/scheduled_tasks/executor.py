"""定时任务执行：唤醒容器 → Agent 跑一轮 → 更新状态 → 可选通知。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select, update

from ..db import ContainerStatus, User, get_session
from ..db.models import ScheduledTask
from ..logging import get_logger
from ..notifications import create_notification
from ..orchestrator import (
    container_name_for,
    ensure_container_ready,
    touch_last_active,
    user_lock,
)
from ..security import decrypt_str
from ..workspaces import ensure_user_default_workspace
from .cron import next_cron_run_utc
from .service import list_due_tasks

log = get_logger("scheduled_executor")

AGENT_RUN_TIMEOUT = 1800.0
TOUCH_INTERVAL_SECONDS = 60.0
STALE_RUNNING_SECONDS = AGENT_RUN_TIMEOUT + 120.0
STALE_ERROR_MESSAGE = "执行中断（超时或服务重启）"

_scan_lock = asyncio.Lock()
_scan_tasks: set[asyncio.Task[None]] = set()


class AgentRunError(Exception):
    def __init__(self, message: str, *, session_id: str | None = None) -> None:
        super().__init__(message)
        self.session_id = session_id


@dataclass(frozen=True)
class _NotifyPayload:
    user_id: int
    task_id: int
    title: str
    notify: bool
    session_id: str | None


def _excerpt(text: str, max_len: int = 160) -> str:
    flat = " ".join(str(text or "").split())
    if len(flat) <= max_len:
        return flat
    return flat[: max_len - 1].rstrip() + "…"


def _parse_agent_error(resp: httpx.Response) -> AgentRunError:
    message = resp.text[:500]
    session_id: str | None = None
    try:
        payload = resp.json()
        detail = payload.get("detail")
        if isinstance(detail, dict):
            session_id = str(detail.get("session_id") or "") or None
            message = str(detail.get("message") or message)
        elif detail is not None:
            message = str(detail)
    except Exception:
        pass
    return AgentRunError(message or f"agent error {resp.status_code}", session_id=session_id)


async def _touch_while_running(user_id: int) -> None:
    try:
        while True:
            await asyncio.sleep(TOUCH_INTERVAL_SECONDS)
            await touch_last_active(user_id)
    except asyncio.CancelledError:
        return


async def _notify_task_result(
    user_id: int,
    *,
    task_id: int,
    title: str,
    notify: bool,
    ok: bool,
    session_id: str | None,
    message: str,
) -> None:
    if not notify:
        return
    link = f"/chat/{session_id}" if session_id else None
    try:
        await create_notification(
            user_id,
            workspace_id=str(task.workspace_id or "").strip() or None,
            kind="success" if ok else "error",
            category="定时任务",
            title=title,
            body=_excerpt(message),
            link=link,
        )
    except Exception as exc:
        log.warning("scheduled_task_notify_failed", task_id=task_id, error=str(exc))


async def _try_claim_task(task_id: int) -> bool:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.enabled.is_(True),
                ScheduledTask.next_run_at.is_not(None),
                ScheduledTask.next_run_at <= now,
                or_(
                    ScheduledTask.last_run_status.is_(None),
                    ScheduledTask.last_run_status != "running",
                ),
            )
            .values(last_run_status="running", last_error=None, updated_at=now)
        )
        return bool(result.rowcount)


async def _call_agent_run(user_id: int, *, workspace_id: str, title: str, prompt: str) -> dict:
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        if user.internal_token_enc is None:
            raise RuntimeError("agent not provisioned")
        token = decrypt_str(user.internal_token_enc)

    status, _meta = await ensure_container_ready(user_id)
    if status != ContainerStatus.RUNNING:
        raise RuntimeError(f"container not running: {status.value}")

    await touch_last_active(user_id)
    container_name = container_name_for(user_id)
    url = f"http://{container_name}:8000/internal/scheduled-run"
    touch_task = asyncio.create_task(_touch_while_running(user_id))
    try:
        async with httpx.AsyncClient(timeout=AGENT_RUN_TIMEOUT) as client:
            resp = await client.post(
                url,
                json={"title": title, "prompt": prompt},
                headers={
                    "X-Internal-Token": token,
                    "X-Workspace-Id": workspace_id,
                },
            )
            if resp.status_code >= 400:
                raise _parse_agent_error(resp)
            return resp.json()
    finally:
        touch_task.cancel()
        await asyncio.gather(touch_task, return_exceptions=True)


async def _finish_task(
    task_id: int,
    *,
    user_id: int,
    ok: bool,
    session_id: str | None,
    error: str | None,
) -> ScheduledTask:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        row = (
            await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        ).scalar_one()
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        tz_name = user.timezone or "UTC"

        row.last_run_at = now
        row.last_run_status = "success" if ok else "failed"
        row.last_session_id = session_id
        row.last_error = error

        if row.schedule_kind == "once":
            row.enabled = False
            row.next_run_at = None
            row.completed_at = now
        elif row.schedule_kind == "cron" and row.enabled and row.cron_expr:
            row.next_run_at = next_cron_run_utc(row.cron_expr, tz_name, base=now)
        else:
            row.next_run_at = None

        await session.flush()
        await session.refresh(row)
        return row


async def recover_stale_running_tasks() -> int:
    """重置超时仍卡在 running 的任务，避免永久不再调度。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=STALE_RUNNING_SECONDS)
    recovered = 0
    notify_queue: list[_NotifyPayload] = []
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ScheduledTask).where(
                    ScheduledTask.last_run_status == "running",
                    ScheduledTask.updated_at < cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            user = (
                await session.execute(select(User).where(User.id == row.user_id))
            ).scalar_one()
            tz_name = user.timezone or "UTC"
            row.last_run_status = "failed"
            row.last_error = STALE_ERROR_MESSAGE
            row.last_run_at = now
            if row.schedule_kind == "once":
                row.enabled = False
                row.next_run_at = None
                row.completed_at = now
            elif row.schedule_kind == "cron" and row.enabled and row.cron_expr:
                row.next_run_at = next_cron_run_utc(row.cron_expr, tz_name, base=now)
            else:
                row.next_run_at = None
            if row.notify:
                notify_queue.append(
                    _NotifyPayload(
                        user_id=row.user_id,
                        task_id=row.id,
                        title=row.title,
                        notify=row.notify,
                        session_id=row.last_session_id,
                    )
                )
            recovered += 1
            log.warning("scheduled_task_stale_recovered", task_id=row.id, user_id=row.user_id)

    for item in notify_queue:
        await _notify_task_result(
            item.user_id,
            task_id=item.task_id,
            title=item.title,
            notify=item.notify,
            ok=False,
            session_id=item.session_id,
            message=STALE_ERROR_MESSAGE,
        )
    return recovered


async def _fail_task(
    task_id: int,
    *,
    user_id: int,
    session_id: str | None,
    err: str,
) -> None:
    finished = await _finish_task(
        task_id,
        user_id=user_id,
        ok=False,
        session_id=session_id,
        error=err,
    )
    await _notify_task_result(
        user_id,
        task_id=task_id,
        title=finished.title,
        notify=finished.notify,
        ok=False,
        session_id=session_id,
        message=err,
    )


async def execute_task(task: ScheduledTask) -> None:
    user_id = task.user_id
    task_id = task.id
    if not await _try_claim_task(task_id):
        return
    log.info("scheduled_task_start", task_id=task_id, user_id=user_id, title=task.title)

    session_id: str | None = None
    try:
        async with get_session() as session:
            user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
            if user.llm_api_key_enc is None:
                raise RuntimeError("LLM 未配置")
            if user.deleted_at is not None:
                raise RuntimeError("用户已删除")

        workspace_id = str(task.workspace_id or "").strip()
        if not workspace_id:
            workspace_id = (await ensure_user_default_workspace(user_id)).id
        result = await _call_agent_run(
            user_id,
            workspace_id=workspace_id,
            title=task.title,
            prompt=task.prompt,
        )
        session_id = str(result.get("session_id") or "") or None
        final_text = str(result.get("final_text") or "")
        finished = await _finish_task(
            task_id,
            user_id=user_id,
            ok=True,
            session_id=session_id,
            error=None,
        )
        await _notify_task_result(
            user_id,
            task_id=task_id,
            title=finished.title,
            notify=finished.notify,
            ok=True,
            session_id=session_id,
            message=final_text or "任务已完成",
        )
        log.info("scheduled_task_done", task_id=task_id, user_id=user_id, session_id=session_id)
    except AgentRunError as exc:
        session_id = exc.session_id or session_id
        err = str(exc) or "unknown error"
        log.warning("scheduled_task_failed", task_id=task_id, user_id=user_id, error=err)
        await _fail_task(task_id, user_id=user_id, session_id=session_id, err=err)
    except Exception as exc:
        err = str(exc) or "unknown error"
        log.warning("scheduled_task_failed", task_id=task_id, user_id=user_id, error=err)
        await _fail_task(task_id, user_id=user_id, session_id=session_id, err=err)


async def _run_user_tasks(tasks: list[ScheduledTask]) -> None:
    if not tasks:
        return
    user_id = tasks[0].user_id
    lock = await user_lock(user_id)
    async with lock:
        for task in tasks:
            await execute_task(task)


async def scan_and_run_due_tasks() -> None:
    # asyncio.wait_for(lock.acquire(), timeout=0) 会在可获取锁时也触发超时，
    # 导致扫描被错误地长期跳过。这里改为显式检测并使用 async with 串行扫描。
    if _scan_lock.locked():
        log.debug("scheduled_task_scan_skipped", reason="already_running")
        return
    async with _scan_lock:
        await recover_stale_running_tasks()
        due = await list_due_tasks()
        if not due:
            return
        by_user: dict[int, list[ScheduledTask]] = defaultdict(list)
        for task in due:
            by_user[task.user_id].append(task)
        await asyncio.gather(*(_run_user_tasks(items) for items in by_user.values()))


def schedule_due_task_scan() -> None:
    """非阻塞触发一轮到期任务扫描；上一轮未完成则跳过。"""
    task = asyncio.create_task(scan_and_run_due_tasks(), name="scheduled-task-scan")
    _scan_tasks.add(task)
    task.add_done_callback(_scan_tasks.discard)
