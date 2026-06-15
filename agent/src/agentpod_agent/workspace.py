"""Request-scoped workspace context and workspace-aware data paths."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path

from .config import get_settings

_DEFAULT_WORKSPACE_ID = "ws_default"
_WORKSPACE_ID_RE = re.compile(r"^ws_[a-z0-9]{8,40}$")
_workspace_id_ctx: ContextVar[str] = ContextVar("workspace_id", default=_DEFAULT_WORKSPACE_ID)


def normalize_workspace_id(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw and _WORKSPACE_ID_RE.fullmatch(raw):
        return raw
    return _DEFAULT_WORKSPACE_ID


def set_workspace_id(value: str | None) -> str:
    normalized = normalize_workspace_id(value)
    _workspace_id_ctx.set(normalized)
    return normalized


def get_workspace_id() -> str:
    return _workspace_id_ctx.get()


def workspaces_root_dir() -> Path:
    return get_settings().data_dir / "workspaces"


def mcp_tool_category(server_name: str, workspace_id: str | None = None) -> str:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()
    return f"mcp:{wid}:{server_name}"


def mcp_tool_category_prefix(workspace_id: str | None = None) -> str:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()
    return f"mcp:{wid}:"


def mcp_tool_full_name(server_name: str, tool_name: str, workspace_id: str | None = None) -> str:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()
    return f"mcp__{wid}__{server_name}__{tool_name}"


def iter_workspace_ids() -> list[str]:
    """列出已有 agent.sqlite 的工作区（供后台任务跨工作区扫描）。"""
    root = workspaces_root_dir()
    ids: list[str] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "agent.sqlite").is_file():
                ids.append(child.name)
    if not ids:
        ids.append(_DEFAULT_WORKSPACE_ID)
    return ids


def workspace_data_dir(workspace_id: str | None = None) -> Path:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()
    root = workspaces_root_dir()
    path = root / wid
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_workspace_storage_initialized(workspace_id: str) -> None:
    """Ensure workspace data directory exists."""
    workspace_data_dir(workspace_id)


async def for_each_workspace(coro: Callable[[str], Awaitable[None]]) -> None:
    """在各工作区 ContextVar 下执行协程（用于启动清理、MCP 恢复等）。"""
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        await coro(wid)

