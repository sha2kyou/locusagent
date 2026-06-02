"""Host → Agent 容器内部请求。"""

from __future__ import annotations

import httpx
from sqlalchemy import select

from .db import ContainerStatus, User, get_session
from .logging import get_logger
from .orchestrator import container_name_for, ensure_container_ready
from .proxy.forward import AGENT_PORT
from .security import decrypt_str

log = get_logger("agent_fetch")


async def agent_get_json(user_id: int, workspace_id: str, path: str) -> dict | None:
    state, _meta = await ensure_container_ready(user_id)
    if state != ContainerStatus.RUNNING:
        return None

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.internal_token_enc is None:
        return None

    internal_token = decrypt_str(user.internal_token_enc)
    target_url = f"http://{container_name_for(user_id)}:{AGENT_PORT}{path}"
    headers = {
        "X-Internal-Token": internal_token,
        "X-User-Id": str(user_id),
        "X-Workspace-Id": workspace_id,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(target_url, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("agent_fetch_failed", user_id=user_id, path=path, error=str(exc))
        return None
    if resp.status_code != 200:
        log.warning("agent_fetch_bad_status", user_id=user_id, path=path, status=resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def agent_post_json(
    user_id: int,
    workspace_id: str,
    path: str,
    *,
    json_body: dict | None = None,
    timeout_s: float = 15.0,
) -> bool:
    state, _meta = await ensure_container_ready(user_id)
    if state != ContainerStatus.RUNNING:
        return False

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.internal_token_enc is None:
        return False

    internal_token = decrypt_str(user.internal_token_enc)
    target_url = f"http://{container_name_for(user_id)}:{AGENT_PORT}{path}"
    headers = {
        "X-Internal-Token": internal_token,
        "X-User-Id": str(user_id),
        "X-Workspace-Id": workspace_id,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
            resp = await client.post(target_url, headers=headers, json=json_body or {})
    except httpx.HTTPError as exc:
        log.warning("agent_post_failed", user_id=user_id, path=path, error=str(exc))
        return False
    if resp.status_code >= 400:
        log.warning(
            "agent_post_bad_status",
            user_id=user_id,
            path=path,
            status=resp.status_code,
            body=resp.text[:200],
        )
        return False
    return True


async def notify_agent_mcp_reconnect(user_id: int, workspace_id: str, server_name: str) -> None:
    ok = await agent_post_json(
        user_id,
        workspace_id,
        "/internal/mcp/reconnect",
        json_body={"server_name": server_name},
    )
    if not ok:
        log.warning(
            "agent_mcp_reconnect_notify_failed",
            user_id=user_id,
            workspace_id=workspace_id,
            server=server_name,
        )


async def notify_agent_mcp_disconnect(user_id: int, workspace_id: str, server_name: str) -> None:
    ok = await agent_post_json(
        user_id,
        workspace_id,
        "/internal/mcp/disconnect",
        json_body={"server_name": server_name},
    )
    if not ok:
        log.warning(
            "agent_mcp_disconnect_notify_failed",
            user_id=user_id,
            workspace_id=workspace_id,
            server=server_name,
        )


async def fetch_mcp_server_config(user_id: int, workspace_id: str, server_name: str) -> dict | None:
    data = await agent_get_json(user_id, workspace_id, "/workspace/mcp")
    if not data:
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("name") == server_name:
            return item
    return None
