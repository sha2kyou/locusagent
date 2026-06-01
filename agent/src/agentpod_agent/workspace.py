"""Request-scoped workspace context and workspace-aware data paths."""

from __future__ import annotations

import re
import shutil
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


def workspace_data_dir(workspace_id: str | None = None) -> Path:
    wid = normalize_workspace_id(workspace_id) if workspace_id is not None else get_workspace_id()
    root = workspaces_root_dir()
    path = root / wid
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_workspace_storage_initialized(workspace_id: str) -> None:
    """Initialize workspace directory and one-time migrate legacy /data layout."""
    settings = get_settings()
    target_dir = workspace_data_dir(workspace_id)
    marker = workspaces_root_dir() / ".legacy-migrated"
    marker_text = ""
    if marker.exists():
        marker_text = marker.read_text(encoding="utf-8", errors="ignore").strip().lower()
        if marker_text.startswith("migrated-to:") or marker_text == "no-legacy":
            return
    legacy_db = settings.data_dir / "agent.sqlite"
    if not legacy_db.exists():
        marker.write_text("no-legacy\n", encoding="utf-8")
        return
    target_db = target_dir / "agent.sqlite"
    should_copy_db = not target_db.exists()
    if target_db.exists():
        legacy_size = legacy_db.stat().st_size
        target_size = target_db.stat().st_size
        # 新建空库通常很小；若旧库明显更大，则覆盖迁移历史数据。
        if target_size <= 512 * 1024 and legacy_size > target_size * 3:
            should_copy_db = True
    if should_copy_db:
        shutil.copy2(legacy_db, target_db)
    for filename in ("mcp.yaml", "tool_settings.yaml"):
        src = settings.data_dir / filename
        if src.exists():
            dst = target_dir / filename
            if should_copy_db or not dst.exists():
                shutil.copy2(src, dst)
    for dirname in ("skills", "workspace"):
        src_dir = settings.data_dir / dirname
        dst_dir = target_dir / dirname
        if src_dir.exists() and (should_copy_db or not dst_dir.exists()):
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
    if should_copy_db:
        marker.write_text(f"migrated-to:{workspace_id}\n", encoding="utf-8")
    elif not marker_text:
        marker.write_text(f"already-present:{workspace_id}\n", encoding="utf-8")

