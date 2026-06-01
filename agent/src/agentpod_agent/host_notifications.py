"""Agent -> Host internal API: unread notifications query client."""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings
from .workspace import get_workspace_id


class HostNotificationsError(RuntimeError):
    pass


def _internal_base_and_headers() -> tuple[str, dict[str, str]]:
    settings = get_settings()
    base = (settings.host_internal_url or "").rstrip("/")
    token = settings.internal_token
    user_id = settings.user_id
    if not base or not token or not user_id:
        raise HostNotificationsError("host internal auth not configured")
    return base, {
        "X-Internal-Token": token,
        "X-User-Id": user_id,
        "X-Workspace-Id": get_workspace_id(),
    }


def _error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "").strip() or f"http {resp.status_code}"
    detail = data.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return str(data)


async def list_unread_notifications(limit: int = 20) -> tuple[list[dict[str, Any]], int]:
    base, headers = _internal_base_and_headers()
    n = max(1, min(int(limit), 200))
    url = f"{base}/internal/notifications?limit={n}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise HostNotificationsError(_error_detail(resp))
    data = resp.json()
    if not isinstance(data, dict):
        raise HostNotificationsError("invalid host response")
    raw_items = data.get("items")
    items = [it for it in raw_items if isinstance(it, dict)] if isinstance(raw_items, list) else []
    count = int(data.get("unread_count") or 0)
    return items, max(0, count)
