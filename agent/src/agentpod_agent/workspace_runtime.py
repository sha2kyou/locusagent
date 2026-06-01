"""Workspace runtime switcher for process-level singletons."""

from __future__ import annotations

import asyncio

from .db import init_db
from .logging import get_logger
from .tool_settings import load_tool_settings
from .tools import registry as tool_registry
from .workspace import ensure_workspace_storage_initialized, get_workspace_id, set_workspace_id

log = get_logger("workspace_runtime")
_runtime_lock = asyncio.Lock()
_active_workspace_id: str | None = None


def _apply_builtin_tool_settings() -> None:
    settings = load_tool_settings()
    for tool in tool_registry.all():
        if tool.category == "builtin":
            tool.enabled = settings.builtin_tools.get(tool.name, True)


async def ensure_workspace_runtime(workspace_id: str) -> None:
    global _active_workspace_id
    workspace_id = set_workspace_id(workspace_id)
    async with _runtime_lock:
        if _active_workspace_id == workspace_id:
            return
        ensure_workspace_storage_initialized(workspace_id)
        init_db()
        from .mcp_.client import start_mcp, stop_mcp

        await stop_mcp()
        _apply_builtin_tool_settings()
        await start_mcp()
        _active_workspace_id = workspace_id
        log.info("workspace_runtime_switched", workspace_id=workspace_id)


def mark_workspace_runtime_bootstrapped() -> None:
    global _active_workspace_id
    _active_workspace_id = get_workspace_id()

