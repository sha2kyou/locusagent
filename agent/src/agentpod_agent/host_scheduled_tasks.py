"""Agent -> Host internal API: scheduled tasks CRUD client."""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


class HostScheduledTasksError(RuntimeError):
    pass


def _internal_base_and_headers() -> tuple[str, dict[str, str]]:
    settings = get_settings()
    base = (settings.host_internal_url or "").rstrip("/")
    token = settings.internal_token
    user_id = settings.user_id
    if not base or not token or not user_id:
        raise HostScheduledTasksError("host internal auth not configured")
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


async def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base, headers = _internal_base_and_headers()
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(method, url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise HostScheduledTasksError(_error_detail(resp))
    data = resp.json()
    if not isinstance(data, dict):
        raise HostScheduledTasksError("invalid host response")
    return data


async def list_scheduled_tasks() -> list[dict[str, Any]]:
    data = await _request("GET", "/internal/scheduled-tasks")
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


async def create_scheduled_task(payload: dict[str, Any]) -> dict[str, Any]:
    data = await _request("POST", "/internal/scheduled-tasks", payload)
    item = data.get("item")
    if not isinstance(item, dict):
        raise HostScheduledTasksError("invalid create response")
    return item


async def update_scheduled_task(task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    data = await _request("PUT", f"/internal/scheduled-tasks/{task_id}", payload)
    item = data.get("item")
    if not isinstance(item, dict):
        raise HostScheduledTasksError("invalid update response")
    return item


async def delete_scheduled_task(task_id: int) -> bool:
    data = await _request("DELETE", f"/internal/scheduled-tasks/{task_id}")
    return bool(data.get("deleted"))
