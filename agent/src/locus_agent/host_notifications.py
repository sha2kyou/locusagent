"""Agent -> Host internal API: unread notifications query client."""

from __future__ import annotations

from typing import Any

import httpx

from .host_internal import HostInternalError, error_detail, internal_base_and_headers
from .workspace import get_workspace_id


class HostNotificationsError(RuntimeError):
    pass


def _internal_base_and_headers() -> tuple[str, dict[str, str]]:
    try:
        return internal_base_and_headers(workspace_id=get_workspace_id())
    except HostInternalError as exc:
        raise HostNotificationsError(str(exc)) from exc


async def list_unread_notifications(limit: int = 20) -> tuple[list[dict[str, Any]], int]:
    base, headers = _internal_base_and_headers()
    n = max(1, min(int(limit), 200))
    url = f"{base}/internal/notifications?limit={n}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise HostNotificationsError(error_detail(resp))
    data = resp.json()
    if not isinstance(data, dict):
        raise HostNotificationsError("invalid host response")
    raw_items = data.get("items")
    items = [it for it in raw_items if isinstance(it, dict)] if isinstance(raw_items, list) else []
    count = int(data.get("unread_count") or 0)
    return items, max(0, count)


async def mark_notification_read(notification_id: int) -> bool:
    base, headers = _internal_base_and_headers()
    url = f"{base}/internal/notifications/{int(notification_id)}/read"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers)
    if resp.status_code >= 400:
        raise HostNotificationsError(error_detail(resp))
    data = resp.json()
    if not isinstance(data, dict):
        raise HostNotificationsError("invalid host response")
    return bool(data.get("ok"))
