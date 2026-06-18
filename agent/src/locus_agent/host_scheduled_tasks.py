"""Agent -> Host internal API: scheduled tasks CRUD client."""

from __future__ import annotations

from typing import Any

import httpx

from .host_internal import HostInternalError, error_detail, internal_base_and_headers
from .workspace import get_workspace_id


class HostScheduledTasksError(RuntimeError):
    pass


def _internal_base_and_headers() -> tuple[str, dict[str, str]]:
    try:
        return internal_base_and_headers(workspace_id=get_workspace_id())
    except HostInternalError as exc:
        raise HostScheduledTasksError(str(exc)) from exc


async def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base, headers = _internal_base_and_headers()
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(method, url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise HostScheduledTasksError(error_detail(resp))
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


async def notify_scheduled_run_started(task_id: int, session_id: str) -> None:
    from .logging import get_logger

    log = get_logger("host_scheduled_tasks")
    try:
        await _request(
            "POST",
            f"/internal/scheduled-tasks/{task_id}/run-started",
            {"session_id": session_id},
        )
    except HostScheduledTasksError as exc:
        log.warning("scheduled_run_started_notify_failed", task_id=task_id, error=str(exc))


async def notify_scheduled_run_finished(
    task_id: int,
    *,
    ok: bool,
    session_id: str,
    final_text: str = "",
    error: str = "",
) -> None:
    from .logging import get_logger

    log = get_logger("host_scheduled_tasks")
    try:
        await _request(
            "POST",
            f"/internal/scheduled-tasks/{task_id}/run-finished",
            {
                "ok": ok,
                "session_id": session_id,
                "final_text": final_text,
                "error": error,
            },
        )
    except HostScheduledTasksError as exc:
        log.warning("scheduled_run_finished_notify_failed", task_id=task_id, error=str(exc))
