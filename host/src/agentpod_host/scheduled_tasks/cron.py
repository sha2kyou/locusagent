"""Cron / 单次调度：按用户时区计算 next_run_at（UTC 存储）。"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


def validate_timezone(name: str) -> str:
    name = (name or "").strip() or "UTC"
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid timezone: {name}") from exc
    return name


def validate_cron(expr: str) -> str:
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("cron expression is required")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron must be 5 fields: minute hour day month weekday")
    try:
        croniter(expr)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"invalid cron expression: {exc}") from exc
    return expr


def parse_local_datetime(value: str, tz_name: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("run_at is required")
    try:
        naive = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("run_at must be ISO datetime, e.g. 2026-05-31T09:00") from exc
    if naive.tzinfo is not None:
        return naive.astimezone(timezone.utc)
    tz = ZoneInfo(validate_timezone(tz_name))
    return naive.replace(tzinfo=tz).astimezone(timezone.utc)


def next_cron_run_utc(cron_expr: str, tz_name: str, *, base: datetime | None = None) -> datetime:
    tz = ZoneInfo(validate_timezone(tz_name))
    now_utc = base or datetime.now(timezone.utc)
    base_local = now_utc.astimezone(tz)
    itr = croniter(validate_cron(cron_expr), base_local)
    nxt_local = itr.get_next(datetime)
    if nxt_local.tzinfo is None:
        nxt_local = nxt_local.replace(tzinfo=tz)
    return nxt_local.astimezone(timezone.utc)


def format_in_timezone(dt: datetime | None, tz_name: str) -> str | None:
    if dt is None:
        return None
    tz = ZoneInfo(validate_timezone(tz_name))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).isoformat()
