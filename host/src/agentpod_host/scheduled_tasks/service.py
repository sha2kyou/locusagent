"""定时任务 CRUD 与 next_run_at 计算。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import or_, select

from ..db import User, get_session
from ..db.models import ScheduledTask
from .cron import format_in_timezone, next_cron_run_utc, parse_local_datetime, validate_cron

ScheduleKind = Literal["once", "cron"]

_BUSY_STATUSES = frozenset({"running", "queued"})


def _ensure_task_not_busy(row: ScheduledTask) -> None:
    if row.last_run_status in _BUSY_STATUSES:
        raise ValueError("task is running")


def _row_to_dict(row: ScheduledTask, *, tz_name: str) -> dict[str, Any]:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "title": row.title,
        "prompt": row.prompt,
        "schedule_kind": row.schedule_kind,
        "cron_expr": row.cron_expr,
        "run_at": format_in_timezone(row.run_at, tz_name),
        "enabled": row.enabled,
        "notify": row.notify,
        "next_run_at": format_in_timezone(row.next_run_at, tz_name),
        "last_run_at": format_in_timezone(row.last_run_at, tz_name),
        "last_run_status": row.last_run_status,
        "last_session_id": row.last_session_id,
        "last_error": row.last_error,
        "completed_at": format_in_timezone(row.completed_at, tz_name),
        "created_at": format_in_timezone(row.created_at, tz_name),
        "updated_at": format_in_timezone(row.updated_at, tz_name),
    }


def _compute_next_run(
    *,
    schedule_kind: str,
    tz_name: str,
    cron_expr: str | None,
    run_at: datetime | None,
    enabled: bool,
) -> datetime | None:
    if not enabled:
        return None
    if schedule_kind == "once":
        return run_at
    if schedule_kind == "cron" and cron_expr:
        return next_cron_run_utc(cron_expr, tz_name)
    return None


async def _load_user_tz(user_id: int) -> str:
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        return user.timezone or "UTC"


async def list_tasks(user_id: int, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
    tz_name = await _load_user_tz(user_id)
    async with get_session() as session:
        stmt = select(ScheduledTask).where(ScheduledTask.user_id == user_id)
        if workspace_id:
            stmt = stmt.where(ScheduledTask.workspace_id == workspace_id)
        rows = (
            await session.execute(
                stmt.order_by(ScheduledTask.created_at.desc())
            )
        ).scalars().all()
        return [_row_to_dict(r, tz_name=tz_name) for r in rows]


async def get_task(user_id: int, task_id: int, *, workspace_id: str | None = None) -> dict[str, Any] | None:
    tz_name = await _load_user_tz(user_id)
    async with get_session() as session:
        stmt = select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user_id,
        )
        if workspace_id:
            stmt = stmt.where(ScheduledTask.workspace_id == workspace_id)
        row = (
            await session.execute(stmt)
        ).scalar_one_or_none()
        return _row_to_dict(row, tz_name=tz_name) if row else None


async def create_task(
    user_id: int,
    *,
    workspace_id: str,
    title: str,
    prompt: str,
    schedule_kind: ScheduleKind,
    enabled: bool = True,
    notify: bool = True,
    cron_expr: str | None = None,
    run_at_local: str | None = None,
) -> dict[str, Any]:
    title = title.strip()
    prompt = prompt.strip()
    if not title:
        raise ValueError("title is required")
    if not prompt:
        raise ValueError("prompt is required")
    if schedule_kind not in ("once", "cron"):
        raise ValueError("schedule_kind must be once or cron")

    tz_name = await _load_user_tz(user_id)
    run_at_utc: datetime | None = None
    cron_value: str | None = None

    if schedule_kind == "once":
        if not run_at_local:
            raise ValueError("run_at is required for once tasks")
        run_at_utc = parse_local_datetime(run_at_local, tz_name)
        now = datetime.now(timezone.utc)
        if run_at_utc <= now:
            raise ValueError("run_at must be in the future")
    else:
        if not cron_expr:
            raise ValueError("cron_expr is required for cron tasks")
        cron_value = validate_cron(cron_expr)

    next_run = _compute_next_run(
        schedule_kind=schedule_kind,
        tz_name=tz_name,
        cron_expr=cron_value,
        run_at=run_at_utc,
        enabled=enabled,
    )

    async with get_session() as session:
        row = ScheduledTask(
            user_id=user_id,
            workspace_id=workspace_id,
            title=title,
            prompt=prompt,
            schedule_kind=schedule_kind,
            cron_expr=cron_value,
            run_at=run_at_utc,
            enabled=enabled,
            notify=notify,
            next_run_at=next_run,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _row_to_dict(row, tz_name=tz_name)


async def update_task(
    user_id: int,
    task_id: int,
    *,
    workspace_id: str | None = None,
    title: str | None = None,
    prompt: str | None = None,
    enabled: bool | None = None,
    notify: bool | None = None,
    cron_expr: str | None = None,
    run_at_local: str | None = None,
) -> dict[str, Any] | None:
    tz_name = await _load_user_tz(user_id)
    async with get_session() as session:
        stmt = select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user_id,
        )
        if workspace_id:
            stmt = stmt.where(ScheduledTask.workspace_id == workspace_id)
        row = (
            await session.execute(stmt)
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.completed_at is not None:
            raise ValueError("completed task cannot be edited")
        _ensure_task_not_busy(row)

        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("title is required")
            row.title = title
        if prompt is not None:
            prompt = prompt.strip()
            if not prompt:
                raise ValueError("prompt is required")
            row.prompt = prompt
        if enabled is not None:
            row.enabled = enabled
        if notify is not None:
            row.notify = notify

        if row.schedule_kind == "once" and run_at_local is not None:
            run_at_utc = parse_local_datetime(run_at_local, tz_name)
            if run_at_utc <= datetime.now(timezone.utc):
                raise ValueError("run_at must be in the future")
            row.run_at = run_at_utc
        elif row.schedule_kind == "cron" and cron_expr is not None:
            row.cron_expr = validate_cron(cron_expr)

        row.next_run_at = _compute_next_run(
            schedule_kind=row.schedule_kind,
            tz_name=tz_name,
            cron_expr=row.cron_expr,
            run_at=row.run_at,
            enabled=row.enabled,
        )
        await session.flush()
        await session.refresh(row)
        return _row_to_dict(row, tz_name=tz_name)


async def delete_task(user_id: int, task_id: int, *, workspace_id: str | None = None) -> bool:
    async with get_session() as session:
        stmt = select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user_id,
        )
        if workspace_id:
            stmt = stmt.where(ScheduledTask.workspace_id == workspace_id)
        row = (
            await session.execute(stmt)
        ).scalar_one_or_none()
        if row is None:
            return False
        _ensure_task_not_busy(row)
        await session.delete(row)
        return True


async def recalc_user_task_schedules(user_id: int) -> None:
    tz_name = await _load_user_tz(user_id)
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ScheduledTask).where(
                    ScheduledTask.user_id == user_id,
                    ScheduledTask.completed_at.is_(None),
                )
            )
        ).scalars().all()
        for row in rows:
            row.next_run_at = _compute_next_run(
                schedule_kind=row.schedule_kind,
                tz_name=tz_name,
                cron_expr=row.cron_expr,
                run_at=row.run_at,
                enabled=row.enabled,
            )


async def list_due_tasks(now: datetime | None = None) -> list[ScheduledTask]:
    now = now or datetime.now(timezone.utc)
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ScheduledTask)
                .where(
                    ScheduledTask.enabled.is_(True),
                    ScheduledTask.next_run_at.is_not(None),
                    ScheduledTask.next_run_at <= now,
                    or_(
                        ScheduledTask.last_run_status.is_(None),
                        ScheduledTask.last_run_status.not_in(["running", "queued"]),
                    ),
                )
                .order_by(ScheduledTask.next_run_at.asc())
            )
        ).scalars().all()
        return list(rows)
