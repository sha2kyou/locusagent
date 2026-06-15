"""定时任务执行：调用 Agent 跑一轮 → 更新状态 → 可选通知。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select, update

from agentpod_shared.settings_store import get_app_timezone

from ..config import get_settings
from ..db import get_session
from ..db.models import ScheduledTask
from ..logging import get_logger
from ..notifications import create_notification
from ..agent_service import agent_url, load_internal_token
from ..workspaces import ensure_default_workspace_row
from .cron import next_cron_run_utc
from .service import get_task, list_due_tasks

log = get_logger("scheduled_executor")

AGENT_RUN_TIMEOUT = 1800.0
STALE_RUNNING_SECONDS = AGENT_RUN_TIMEOUT + 120.0
STALE_ERROR_MESSAGE = "执行中断（超时或服务重启）"

_scan_lock = asyncio.Lock()
_scan_tasks: set[asyncio.Task[None]] = set()


class AgentRunError(Exception):
    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.session_id = session_id
        self.status_code = status_code


@dataclass(frozen=True)
class _NotifyPayload:
    task_id: int
    workspace_id: str | None
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
    return AgentRunError(
        message or f"agent error {resp.status_code}",
        session_id=session_id,
        status_code=resp.status_code,
    )


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, AgentRunError) and exc.status_code in {429, 502, 503, 504}:
        return True
    msg = str(exc or "").strip().lower()
    if not msg:
        return False
    if "internal token missing" in msg:
        return False
    transient_hints = (
        "timeout",
        "timed out",
        "unreachable",
        "temporarily",
        "connection",
        "connect",
        "container not running",
        "http 429",
        "http 502",
        "http 503",
    )
    return any(hint in msg for hint in transient_hints)



async def _notify_task_result(
    *,
    task_id: int,
    workspace_id: str | None,
    title: str,
    notify: bool,
    ok: bool,
    session_id: str | None,
    message: str,
) -> None:
    if not notify:
        return
    link = "/scheduled-tasks" if session_id else None
    try:
        await create_notification(
            workspace_id=workspace_id,
            kind="success" if ok else "error",
            category="定时任务",
            title=title,
            body=_excerpt(message),
            link=link,
        )
    except Exception as exc:
        log.warning("scheduled_task_notify_failed", task_id=task_id, error=str(exc))


async def _mark_task_queued(task_id: int) -> bool:
    """CAS 标记任务为 queued，防止多轮扫描重复入队。"""
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
                    ScheduledTask.last_run_status.not_in(["running", "queued"]),
                ),
            )
            .values(
                last_run_status="queued",
                last_error=None,
                updated_at=now,
                active_run_manual=False,
            )
        )
        return bool(result.rowcount)


async def _rollback_queued_state(task_id: int, reason: str) -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        await session.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id, ScheduledTask.last_run_status == "queued")
            .values(last_run_status=None, last_error=reason, updated_at=now)
        )


async def _try_claim_manual_task(task_id: int) -> bool:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.completed_at.is_(None),
                ScheduledTask.last_run_status == "queued",
            )
            .values(last_run_status="running", last_error=None, updated_at=now)
        )
        return bool(result.rowcount)


async def _mark_manual_task_queued(task_id: int) -> bool:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.completed_at.is_(None),
                or_(
                    ScheduledTask.last_run_status.is_(None),
                    ScheduledTask.last_run_status.not_in(["running", "queued"]),
                ),
            )
            .values(
                last_run_status="queued",
                last_error=None,
                updated_at=now,
                active_run_manual=True,
            )
        )
        return bool(result.rowcount)


async def trigger_task_run(
    task_id: int,
    *,
    workspace_id: str | None = None,
) -> dict:
    async with get_session() as session:
        stmt = select(ScheduledTask).where(ScheduledTask.id == task_id)
        if workspace_id:
            stmt = stmt.where(ScheduledTask.workspace_id == workspace_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ValueError("task not found")
        if row.completed_at is not None:
            raise ValueError("task already completed")
        if row.last_run_status in ("running", "queued"):
            raise ValueError("task already running")

    if not await _mark_manual_task_queued(task_id):
        raise ValueError("task already running")

    asyncio.create_task(execute_task_by_id(task_id, manual=True), name=f"scheduled-manual-{task_id}")

    item = await get_task(task_id, workspace_id=workspace_id)
    if item is None:
        raise ValueError("task not found")
    return item


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
                ScheduledTask.last_run_status == "queued",
            )
            .values(last_run_status="running", last_error=None, updated_at=now)
        )
        return bool(result.rowcount)


async def _call_agent_run(
    *,
    workspace_id: str,
    title: str,
    prompt: str,
    task_id: int,
) -> dict:
    token = await load_internal_token()
    if token is None:
        raise RuntimeError("internal token missing")

    url = agent_url("/internal/scheduled-run")
    async with httpx.AsyncClient(timeout=AGENT_RUN_TIMEOUT) as client:
        resp = await client.post(
            url,
            json={"title": title, "prompt": prompt, "task_id": task_id},
            headers={
                "X-Internal-Token": token,
                "X-Workspace-Id": workspace_id,
            },
        )
        if resp.status_code >= 400:
            raise _parse_agent_error(resp)
        return resp.json()


def _app_timezone() -> str:
    return get_app_timezone()


async def _finish_task(
    task_id: int,
    *,
    ok: bool,
    session_id: str | None,
    error: str | None,
    manual: bool = False,
    summary: str | None = None,
) -> ScheduledTask | None:
    now = datetime.now(timezone.utc)
    tz_name = _app_timezone()
    async with get_session() as session:
        row = (
            await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        ).scalar_one()
        if row.last_run_status in ("success", "failed"):
            return None
        manual = manual or bool(row.active_run_manual)

        row.last_run_at = now
        row.last_run_status = "success" if ok else "failed"
        row.last_session_id = session_id
        row.last_error = error
        row.active_run_session_id = None
        row.active_run_manual = False
        if ok:
            row.last_run_summary = _excerpt(summary or "", max_len=2000) or None
        else:
            row.last_run_summary = None

        if manual and row.schedule_kind == "once":
            pass
        elif manual and row.schedule_kind == "cron" and not row.enabled:
            pass
        elif row.schedule_kind == "once":
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


async def _probe_agent_scheduled_session(
    *,
    workspace_id: str,
    session_id: str,
) -> dict:
    token = await load_internal_token()
    if token is None:
        raise RuntimeError("internal token missing")

    url = agent_url(f"/internal/scheduled-run-status/{session_id}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={
                "X-Internal-Token": token,
                "X-Workspace-Id": workspace_id,
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(resp.text[:200] or f"agent error {resp.status_code}")
        data = resp.json()
        return data if isinstance(data, dict) else {}


async def complete_task_run_from_agent(
    task_id: int,
    *,
    workspace_id: str | None,
    ok: bool,
    session_id: str,
    final_text: str = "",
    error: str = "",
) -> bool:
    """Agent 回调收尾；若 Host 已写入终态则幂等跳过。返回是否新完成。"""
    sid = str(session_id or "").strip()
    finished = await _finish_task(
        task_id,
        ok=ok,
        session_id=sid or None,
        error=(error or None) if not ok else None,
        summary=final_text if ok else None,
    )
    if finished is None:
        return False
    await _notify_task_result(
        task_id=task_id,
        workspace_id=str(finished.workspace_id or "").strip() or None,
        title=finished.title,
        notify=finished.notify,
        ok=ok,
        session_id=sid or None,
        message=final_text if ok else (error or "任务失败"),
    )
    log.info(
        "scheduled_task_callback_done",
        task_id=task_id,
        ok=ok,
        session_id=sid,
    )
    return True


async def reconcile_interrupted_scheduled_tasks() -> int:
    """Host 重启后对齐 Agent 已完成的运行，或立即释放无会话跟踪的僵死任务。"""
    reconciled = 0
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ScheduledTask).where(
                    ScheduledTask.last_run_status.in_(["running", "queued"]),
                )
            )
        ).scalars().all()
        snapshots = [
            (
                row.id,
                str(row.workspace_id or "").strip(),
                str(row.active_run_session_id or "").strip() or None,
            )
            for row in rows
        ]

    for task_id, workspace_id, active_session_id in snapshots:
        if active_session_id and workspace_id:
            try:
                probe = await _probe_agent_scheduled_session(
                    workspace_id=workspace_id,
                    session_id=active_session_id,
                )
                status = str(probe.get("status") or "").strip()
                if status == "completed":
                    if await complete_task_run_from_agent(
                        task_id,
                        workspace_id=workspace_id,
                        ok=True,
                        session_id=active_session_id,
                        final_text=str(probe.get("final_text") or ""),
                    ):
                        reconciled += 1
                    continue
                if status == "failed":
                    if await complete_task_run_from_agent(
                        task_id,
                        workspace_id=workspace_id,
                        ok=False,
                        session_id=active_session_id,
                        error=str(probe.get("error") or STALE_ERROR_MESSAGE),
                    ):
                        reconciled += 1
                    continue
                if status == "running":
                    continue
            except Exception as exc:
                log.warning(
                    "scheduled_task_reconcile_probe_failed",
                    task_id=task_id,
                    error=str(exc),
                )

        await _fail_task(
            task_id,
            session_id=active_session_id,
            err=STALE_ERROR_MESSAGE,
        )
        reconciled += 1
        log.warning("scheduled_task_reconcile_interrupted", task_id=task_id)

    return reconciled


async def recover_stale_running_tasks() -> int:
    """重置超时仍卡在 running 的任务，避免永久不再调度。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=STALE_RUNNING_SECONDS)
    tz_name = _app_timezone()
    recovered = 0
    notify_queue: list[_NotifyPayload] = []
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ScheduledTask).where(
                    ScheduledTask.last_run_status.in_(["running", "queued"]),
                    ScheduledTask.updated_at < cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            row.last_run_status = "failed"
            row.last_error = STALE_ERROR_MESSAGE
            row.last_run_at = now
            row.active_run_session_id = None
            row.active_run_manual = False
            row.last_run_summary = None
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
                        task_id=row.id,
                        workspace_id=str(row.workspace_id or "").strip() or None,
                        title=row.title,
                        notify=row.notify,
                        session_id=row.last_session_id,
                    )
                )
            recovered += 1
            log.warning("scheduled_task_stale_recovered", task_id=row.id)

    for item in notify_queue:
        await _notify_task_result(
            task_id=item.task_id,
            workspace_id=item.workspace_id,
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
    session_id: str | None,
    err: str,
    manual: bool = False,
) -> None:
    finished = await _finish_task(
        task_id,
        ok=False,
        session_id=session_id,
        error=err,
        manual=manual,
    )
    if finished is None:
        return
    await _notify_task_result(
        task_id=task_id,
        workspace_id=str(finished.workspace_id or "").strip() or None,
        title=finished.title,
        notify=finished.notify,
        ok=False,
        session_id=session_id,
        message=err,
    )


async def execute_task_by_id(task_id: int, *, manual: bool = False) -> None:
    async with get_session() as session:
        task = (
            await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        ).scalar_one_or_none()
    if task is None:
        return
    if manual:
        if not await _try_claim_manual_task(task_id):
            return
    elif not await _try_claim_task(task_id):
        return
    log.info(
        "scheduled_task_start",
        task_id=task_id,
        title=task.title,
        manual=manual,
    )
    settings = get_settings()
    max_attempts = max(1, int(settings.scheduled_task_retry_max_attempts))
    delay_seconds = max(0.1, float(settings.scheduled_task_retry_initial_delay_seconds))
    max_delay_seconds = max(delay_seconds, float(settings.scheduled_task_retry_max_delay_seconds))
    backoff_multiplier = max(1.0, float(settings.scheduled_task_retry_backoff_multiplier))

    session_id: str | None = None
    attempt = 0
    while True:
        attempt += 1
        try:
            workspace_id = str(task.workspace_id or "").strip()
            if not workspace_id:
                workspace_id = (await ensure_default_workspace_row()).id
            result = await _call_agent_run(
                workspace_id=workspace_id,
                title=task.title,
                prompt=task.prompt,
                task_id=task_id,
            )
            session_id = str(result.get("session_id") or "") or None
            final_text = str(result.get("final_text") or "")
            finished = await _finish_task(
                task_id,
                ok=True,
                session_id=session_id,
                error=None,
                manual=manual,
                summary=final_text,
            )
            if finished is None:
                log.info("scheduled_task_already_finished", task_id=task_id)
                return
            await _notify_task_result(
                task_id=task_id,
                workspace_id=str(finished.workspace_id or "").strip() or None,
                title=finished.title,
                notify=finished.notify,
                ok=True,
                session_id=session_id,
                message=final_text or "任务已完成",
            )
            log.info(
                "scheduled_task_done",
                task_id=task_id,
                session_id=session_id,
                attempts=attempt,
            )
            return
        except AgentRunError as exc:
            session_id = exc.session_id or session_id
            err = str(exc) or "unknown error"
            retryable = _is_retryable_exception(exc)
        except Exception as exc:
            err = str(exc) or "unknown error"
            retryable = _is_retryable_exception(exc)

        if retryable and attempt < max_attempts:
            log.warning(
                "scheduled_task_retrying",
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
                delay_seconds=delay_seconds,
                error=err,
            )
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(max_delay_seconds, delay_seconds * backoff_multiplier)
            continue

        log.warning(
            "scheduled_task_failed",
            task_id=task_id,
            attempts=attempt,
            retryable=retryable,
            error=err,
        )
        await _fail_task(task_id, session_id=session_id, err=err, manual=manual)
        return


async def scan_and_run_due_tasks() -> None:
    if _scan_lock.locked():
        log.debug("scheduled_task_scan_skipped", reason="already_running")
        return
    async with _scan_lock:
        await recover_stale_running_tasks()
        due = await list_due_tasks()
        if not due:
            return
        for task in due:
            if not await _mark_task_queued(task.id):
                continue
            asyncio.create_task(
                execute_task_by_id(task.id),
                name=f"scheduled-due-{task.id}",
            )


def schedule_due_task_scan() -> None:
    """非阻塞触发一轮到期任务扫描；上一轮未完成则跳过。"""
    task = asyncio.create_task(scan_and_run_due_tasks(), name="scheduled-task-scan")
    _scan_tasks.add(task)
    task.add_done_callback(_scan_tasks.discard)
