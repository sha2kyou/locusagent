"""Host → Agent 内部请求。"""

from __future__ import annotations

import httpx

from .agent_service import agent_url, load_internal_token
from .logging import get_logger

log = get_logger("agent_fetch")


async def agent_get_json(workspace_id: str, path: str) -> dict | None:
    internal_token = await load_internal_token()
    if internal_token is None:
        return None

    target_url = agent_url(path)
    headers = {
        "X-Internal-Token": internal_token,
        "X-Workspace-Id": workspace_id,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(target_url, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("agent_fetch_failed", path=path, error=str(exc))
        return None
    if resp.status_code != 200:
        log.warning("agent_fetch_bad_status", path=path, status=resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def agent_post_json(
    workspace_id: str,
    path: str,
    *,
    json_body: dict | None = None,
    timeout_s: float = 15.0,
) -> bool:
    internal_token = await load_internal_token()
    if internal_token is None:
        return False

    target_url = agent_url(path)
    headers = {
        "X-Internal-Token": internal_token,
        "X-Workspace-Id": workspace_id,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
            resp = await client.post(target_url, headers=headers, json=json_body or {})
    except httpx.HTTPError as exc:
        log.warning("agent_post_failed", path=path, error=str(exc))
        return False
    if resp.status_code >= 400:
        log.warning(
            "agent_post_bad_status",
            path=path,
            status=resp.status_code,
            body=resp.text[:200],
        )
        return False
    return True


async def notify_agent_mcp_reconnect(workspace_id: str, server_name: str) -> None:
    ok = await agent_post_json(
        workspace_id,
        "/internal/mcp/reconnect",
        json_body={"server_name": server_name},
    )
    if not ok:
        log.warning(
            "agent_mcp_reconnect_notify_failed",
            workspace_id=workspace_id,
            server=server_name,
        )


async def notify_agent_mcp_disconnect(workspace_id: str, server_name: str) -> None:
    ok = await agent_post_json(
        workspace_id,
        "/internal/mcp/disconnect",
        json_body={"server_name": server_name},
    )
    if not ok:
        log.warning(
            "agent_mcp_disconnect_notify_failed",
            workspace_id=workspace_id,
            server=server_name,
        )


async def fetch_mcp_server_config(workspace_id: str, server_name: str) -> dict | None:
    data = await agent_get_json(workspace_id, "/workspace/mcp")
    if not data:
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("name") == server_name:
            return item
    return None
