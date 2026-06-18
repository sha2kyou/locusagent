"""Request-scoped workspace context and workspace-aware data paths."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path

from locus_shared.workspace_ids import is_valid_workspace_id, normalize_workspace_id

from .config import get_settings

_workspace_id_ctx: ContextVar[str] = ContextVar("workspace_id", default="")


def set_workspace_id(value: str | None) -> str:
    normalized = normalize_workspace_id(value)
    _workspace_id_ctx.set(normalized)
    return normalized


def get_workspace_id() -> str:
    return _workspace_id_ctx.get()


def workspaces_root_dir() -> Path:
    return get_settings().data_dir / "workspaces"


def mcp_tool_category(server_name: str, workspace_id: str | None = None) -> str:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else normalize_workspace_id(get_workspace_id())
    return f"mcp:{wid}:{server_name}"


def mcp_tool_category_prefix(workspace_id: str | None = None) -> str:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else normalize_workspace_id(get_workspace_id())
    return f"mcp:{wid}:"


def mcp_tool_full_name(server_name: str, tool_name: str, workspace_id: str | None = None) -> str:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else normalize_workspace_id(get_workspace_id())
    return f"mcp__{wid}__{server_name}__{tool_name}"


def iter_workspace_ids() -> list[str]:
    """列出已有 agent.sqlite 的工作区（供后台任务跨工作区扫描）。"""
    root = workspaces_root_dir()
    ids: list[str] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not (child / "agent.sqlite").is_file():
                continue
            wid = child.name.strip().lower()
            if is_valid_workspace_id(wid):
                ids.append(wid)
    return ids


def workspace_data_dir(workspace_id: str | None = None) -> Path:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else normalize_workspace_id(get_workspace_id())
    root = workspaces_root_dir()
    path = root / wid
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_workspace_storage_initialized(workspace_id: str) -> None:
    workspace_data_dir(workspace_id)


async def for_each_workspace(coro: Callable[[str], Awaitable[None]]) -> None:
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        await coro(wid)
