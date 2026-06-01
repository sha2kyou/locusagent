"""Agent -> Host internal API: settings query client."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .config import get_settings
from .logging import get_logger

log = get_logger("host_settings")

_TZ_CACHE_TTL_SECONDS = 60.0
_tz_cache: tuple[str, float] | None = None
_tz_cache_lock = asyncio.Lock()


class HostSettingsError(RuntimeError):
    pass


def _internal_base_and_headers() -> tuple[str, dict[str, str]]:
    settings = get_settings()
    base = (settings.host_internal_url or "").rstrip("/")
    token = settings.internal_token
    user_id = settings.user_id
    if not base or not token or not user_id:
        raise HostSettingsError("host internal auth not configured")
    return base, {"X-Internal-Token": token, "X-User-Id": user_id}


def _error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "").strip() or f"http {resp.status_code}"
    detail = data.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return str(data)


async def _fetch_timezone_from_host() -> str:
    base, headers = _internal_base_and_headers()
    url = f"{base}/internal/settings/timezone"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise HostSettingsError(_error_detail(resp))
    data = resp.json()
    if not isinstance(data, dict):
        raise HostSettingsError("invalid host response")
    tz = str(data.get("timezone") or "").strip()
    if not tz:
        raise HostSettingsError("missing timezone in host response")
    return tz


async def get_timezone(*, force_refresh: bool = False) -> str:
    """读取 Host 用户设置时区；60s 进程内缓存，避免每轮对话重复请求。"""
    global _tz_cache
    now = time.monotonic()
    if not force_refresh and _tz_cache is not None:
        tz, expires = _tz_cache
        if now < expires:
            return tz

    async with _tz_cache_lock:
        if not force_refresh and _tz_cache is not None:
            tz, expires = _tz_cache
            if time.monotonic() < expires:
                return tz
        try:
            tz = await _fetch_timezone_from_host()
        except HostSettingsError as exc:
            if _tz_cache is not None:
                log.debug("timezone_fetch_failed_use_stale", error=str(exc))
                return _tz_cache[0]
            raise
        _tz_cache = (tz, time.monotonic() + _TZ_CACHE_TTL_SECONDS)
        return tz


async def build_runtime_time_context() -> str:
    """基于 Host 用户设置时区生成本轮时间上下文。"""
    now_utc = datetime.now(UTC)
    tz_name = "UTC"
    local_dt = now_utc
    try:
        tz_name = await get_timezone()
        local_dt = now_utc.astimezone(ZoneInfo(tz_name))
    except HostSettingsError as exc:
        log.debug("timezone_fetch_failed", error=str(exc))
    except ZoneInfoNotFoundError as exc:
        log.warning("timezone_invalid", timezone=tz_name, error=str(exc))
        tz_name = "UTC"

    return (
        "## Runtime Time Context\n"
        f"- Current UTC time: {now_utc.isoformat()}\n"
        f"- User timezone: {tz_name}\n"
        f"- Current user local time: {local_dt.isoformat()}\n"
        "When user asks for current date/time, use Current user local time."
    )
