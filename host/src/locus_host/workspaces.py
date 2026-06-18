"""Workspace helpers: default workspace bootstrap and request-time resolution."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from locus_shared.settings_store import data_dir
from locus_shared.workspace_ids import (
    generate_workspace_id,
    is_valid_workspace_id,
    normalize_workspace_id,
)
from fastapi import Request
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import McpOauthCredential, Workspace, get_session


def normalize_workspace_name(name: str | None) -> str:
    value = (name or "").strip()
    return value[:25] if value else "默认工作区"


def normalize_workspace_description(description: str | None) -> str:
    value = (description or "").strip()
    return value[:200]


_COPY_SUFFIX = " 副本"

_CONVERSATION_TABLES = (
    "message_attachments",
    "messages",
    "attachments",
    "runs",
    "session_todos",
    "sessions",
)


def suggest_workspace_copy_name(source_name: str) -> str:
    suffix = _COPY_SUFFIX
    max_base = 25 - len(suffix)
    if max_base < 1:
        return suffix.strip()[:25]
    base = source_name.strip()[:max_base].rstrip()
    return f"{base}{suffix}" if base else suffix.strip()[:25]


def _strip_conversation_data(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        existing = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in _CONVERSATION_TABLES:
            if table in existing:
                conn.execute(f"DELETE FROM {table}")
        if "messages_fts" in existing:
            conn.execute("DELETE FROM messages_fts")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def copy_workspace_on_disk(source_id: str, target_id: str) -> None:
    src = _workspaces_root() / source_id
    dst = _workspaces_root() / target_id
    if not (src / "agent.sqlite").is_file():
        raise FileNotFoundError(f"workspace data not found: {source_id}")
    if dst.exists():
        raise FileExistsError(f"workspace already exists: {target_id}")
    shutil.copytree(src, dst)
    _strip_conversation_data(dst / "agent.sqlite")


def delete_workspace_on_disk(workspace_id: str) -> None:
    path = _workspaces_root() / workspace_id
    if path.is_dir():
        shutil.rmtree(path)


async def copy_mcp_oauth_credentials(
    session: AsyncSession,
    *,
    source_id: str,
    target_id: str,
) -> None:
    rows = (
        await session.execute(
            select(McpOauthCredential).where(McpOauthCredential.workspace_id == source_id)
        )
    ).scalars().all()
    for row in rows:
        session.add(
            McpOauthCredential(
                workspace_id=target_id,
                server_name=row.server_name,
                server_url=row.server_url,
                tokens_enc=row.tokens_enc,
                client_info_enc=row.client_info_enc,
            )
        )
    await session.flush()


def requested_workspace_id(request: Request) -> str | None:
    raw = request.headers.get("X-Workspace-Id") or request.query_params.get("workspace_id")
    value = (raw or "").strip().lower()
    if not value:
        return None
    return value if is_valid_workspace_id(value) else None


def _base_query() -> Select[tuple[Workspace]]:
    return select(Workspace)


def _workspaces_root() -> Path:
    return data_dir() / "workspaces"


def workspace_dirs_on_disk() -> list[str]:
    root = _workspaces_root()
    ids: list[str] = []
    if not root.is_dir():
        return ids
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "agent.sqlite").is_file():
            wid = child.name.strip().lower()
            if is_valid_workspace_id(wid):
                ids.append(wid)
    return ids


def agent_sqlite_session_count(workspace_id: str) -> int:
    db_path = _workspaces_root() / workspace_id / "agent.sqlite"
    if not db_path.is_file():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def preferred_default_workspace_id(candidates: list[str]) -> str:
    valid = [wid for wid in candidates if is_valid_workspace_id(wid)]
    if not valid:
        return generate_workspace_id()
    return max(valid, key=agent_sqlite_session_count)


def _workspace_display_name(workspace_id: str) -> str:
    return f"工作区 {workspace_id[3:11]}"


async def sync_workspaces_from_disk(session: AsyncSession) -> None:
    """将磁盘上已有 agent.sqlite 的工作区补登记到 host.sqlite。"""
    disk_ids = workspace_dirs_on_disk()
    if not disk_ids:
        return
    rows = (await session.execute(_base_query())).scalars().all()
    known = {row.id for row in rows}
    for wid in disk_ids:
        if wid in known:
            continue
        session.add(
            Workspace(
                id=wid,
                name=_workspace_display_name(wid),
                description="",
                is_default=False,
            )
        )
    await session.flush()


async def ensure_default_workspace(session: AsyncSession) -> Workspace:
    await sync_workspaces_from_disk(session)

    default = (
        await session.execute(_base_query().where(Workspace.is_default.is_(True)))
    ).scalar_one_or_none()
    if default is not None:
        return default

    existing = (
        await session.execute(_base_query().order_by(Workspace.created_at.asc(), Workspace.id.asc()))
    ).scalars().all()
    if existing:
        preferred_id = preferred_default_workspace_id([row.id for row in existing])
        chosen = next(row for row in existing if row.id == preferred_id)
        for row in existing:
            row.is_default = row.id == chosen.id
        await session.flush()
        return chosen

    disk_ids = workspace_dirs_on_disk()
    wid = preferred_default_workspace_id(disk_ids)
    ws = Workspace(
        id=wid,
        name="默认工作区",
        description="",
        is_default=True,
    )
    session.add(ws)
    await session.flush()
    return ws


async def ensure_default_workspace_row() -> Workspace:
    async with get_session() as session:
        return await ensure_default_workspace(session)


async def resolve_workspace(
    session: AsyncSession,
    *,
    workspace_id: str | None,
) -> Workspace:
    default = await ensure_default_workspace(session)
    if not workspace_id:
        return default
    if not is_valid_workspace_id(workspace_id):
        return default
    row = (
        await session.execute(
            _base_query().where(Workspace.id == normalize_workspace_id(workspace_id)).limit(1)
        )
    ).scalar_one_or_none()
    return row or default
