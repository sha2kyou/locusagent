"""Workspace runtime switcher for process-level singletons."""

from __future__ import annotations

import asyncio
from typing import Any

from .db import init_db
from .logging import get_logger
from .tool_settings import load_tool_settings
from .tools import registry as tool_registry
from .workspace import ensure_workspace_storage_initialized, get_workspace_id, normalize_workspace_id, set_workspace_id

log = get_logger("workspace_runtime")
_runtime_lock = asyncio.Lock()
_active_workspace_id: str | None = None
_mcp_ready_workspace: str | None = None
_mcp_warm_inflight: set[str] = set()


def _apply_builtin_tool_settings() -> None:
    settings = load_tool_settings()
    for tool in tool_registry.all():
        if tool.category == "builtin":
            tool.enabled = settings.builtin_tools.get(tool.name, True)


def invalidate_mcp_runtime(workspace_id: str | None = None) -> None:
    """清除 MCP 就绪缓存；OAuth 授权、重连或 mcp.yaml 变更后需调用。"""
    global _mcp_ready_workspace
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()
    if _mcp_ready_workspace is None or _mcp_ready_workspace == wid:
        _mcp_ready_workspace = None


def mark_mcp_runtime_ready(workspace_id: str | None = None) -> None:
    global _mcp_ready_workspace
    _mcp_ready_workspace = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()


async def ensure_workspace_context(workspace_id: str) -> None:
    """轻量工作区切换：DB/内置工具；不连接 MCP（避免阻塞 sessions 等只读 API）。"""
    global _active_workspace_id, _mcp_ready_workspace
    workspace_id = set_workspace_id(workspace_id)
    async with _runtime_lock:
        same_workspace = _active_workspace_id == workspace_id
        if not same_workspace:
            ensure_workspace_storage_initialized(workspace_id)
            init_db()
            removed = tool_registry.unregister_mcp_tools_outside_workspace(workspace_id)
            if removed:
                log.info("mcp_tools_purged_for_workspace_switch", removed=removed, workspace_id=workspace_id)
            # 仅真实切换工作区时失效 MCP 缓存；首次请求 / 容器 bootstrap 不清除预热结果。
            if _active_workspace_id is not None:
                _mcp_ready_workspace = None
                log.info(
                    "workspace_runtime_switched",
                    workspace_id=workspace_id,
                    previous_workspace_id=_active_workspace_id,
                )
        _apply_builtin_tool_settings()
        _active_workspace_id = workspace_id


async def _ensure_mcp_runtime_inner(workspace_id: str) -> None:
    global _mcp_ready_workspace
    await ensure_workspace_context(workspace_id)
    wid = get_workspace_id()
    if _mcp_ready_workspace == wid:
        return
    from .mcp_.client import ensure_mcp_started, sync_mcp_tools_for_workspace

    await ensure_mcp_started(wid)
    await sync_mcp_tools_for_workspace(wid)
    _mcp_ready_workspace = wid


async def ensure_mcp_runtime(workspace_id: str) -> None:
    """连接 MCP 并注册工具；MCP 管理页 sync 等显式同步路径使用（带总超时）。"""
    from .config import get_settings

    settings = get_settings()
    timeout = max(30.0, float(settings.mcp_connect_timeout_seconds) * 3.0)
    try:
        await asyncio.wait_for(_ensure_mcp_runtime_inner(workspace_id), timeout=timeout)
    except TimeoutError:
        log.warning("mcp_runtime_sync_timeout", workspace_id=normalize_workspace_id(workspace_id), timeout_seconds=timeout)


async def refresh_mcp_server(workspace_id: str, server_name: str) -> dict[str, Any]:
    """单服重连并同步工具（OAuth 完成 / 手动重连）。"""
    from .mcp_.client import ensure_mcp_started, reconnect_mcp_server, sync_mcp_tools_for_workspace

    wid = set_workspace_id(workspace_id)
    invalidate_mcp_runtime(wid)
    await ensure_workspace_context(wid)
    await ensure_mcp_started(wid)
    try:
        runtime = await reconnect_mcp_server(server_name)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning("mcp_refresh_failed", server=server_name, workspace_id=wid, error=str(exc))
        runtime = {"name": server_name, "connected": False, "tools": [], "error": str(exc)}
    if runtime.get("connected"):
        await sync_mcp_tools_for_workspace(wid)
        mark_mcp_runtime_ready(wid)
    return runtime


async def disconnect_mcp_server_runtime(workspace_id: str, server_name: str) -> bool:
    from .mcp_.client import disconnect_mcp_server, ensure_mcp_started

    wid = set_workspace_id(workspace_id)
    invalidate_mcp_runtime(wid)
    await ensure_workspace_context(wid)
    await ensure_mcp_started(wid)
    ok = await disconnect_mcp_server(server_name)
    mark_mcp_runtime_ready(wid)
    return ok


async def ensure_workspace_runtime(workspace_id: str) -> None:
    """兼容旧调用：等价于 ensure_mcp_runtime。"""
    await ensure_mcp_runtime(workspace_id)


def mark_workspace_runtime_bootstrapped() -> None:
    global _active_workspace_id
    _active_workspace_id = get_workspace_id()


async def warm_mcp_runtime_background(workspace_id: str) -> None:
    wid = normalize_workspace_id(workspace_id)
    if _mcp_ready_workspace == wid or wid in _mcp_warm_inflight:
        return
    _mcp_warm_inflight.add(wid)
    try:
        await ensure_mcp_runtime(wid)
    except Exception as exc:
        log.warning("mcp_warm_failed", workspace_id=wid, error=str(exc))
    finally:
        _mcp_warm_inflight.discard(wid)


def schedule_mcp_runtime_warm(workspace_id: str) -> None:
    """后台预热 MCP，不阻塞列表等只读接口。"""
    wid = normalize_workspace_id(workspace_id)
    if _mcp_ready_workspace == wid or wid in _mcp_warm_inflight:
        return
    asyncio.create_task(warm_mcp_runtime_background(wid), name=f"mcp-warm-{wid}")
