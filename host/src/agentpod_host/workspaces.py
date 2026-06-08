"""Workspace helpers: default workspace bootstrap and request-time resolution."""

from __future__ import annotations

import re
import secrets

from fastapi import Request
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Workspace, get_session

_WORKSPACE_ID_RE = re.compile(r"^ws_[a-z0-9]{8,40}$")


def generate_workspace_id() -> str:
    return f"ws_{secrets.token_hex(10)}"


def normalize_workspace_name(name: str | None) -> str:
    value = (name or "").strip()
    return value[:25] if value else "默认工作区"


def normalize_workspace_description(description: str | None) -> str:
    value = (description or "").strip()
    return value[:200]


def is_valid_workspace_id(workspace_id: str | None) -> bool:
    return bool(workspace_id and _WORKSPACE_ID_RE.fullmatch(workspace_id))


def requested_workspace_id(request: Request) -> str | None:
    raw = request.headers.get("X-Workspace-Id") or request.query_params.get("workspace_id")
    value = (raw or "").strip().lower()
    if not value:
        return None
    return value if is_valid_workspace_id(value) else None


def _base_query() -> Select[tuple[Workspace]]:
    return select(Workspace)


async def ensure_default_workspace(session: AsyncSession) -> Workspace:
    default = (
        await session.execute(_base_query().where(Workspace.is_default.is_(True)))
    ).scalar_one_or_none()
    if default is not None:
        return default
    existing = (
        await session.execute(_base_query().order_by(Workspace.created_at.asc(), Workspace.id.asc()))
    ).scalars().all()
    if existing:
        ws = existing[0]
        ws.is_default = True
        return ws
    ws = Workspace(
        id=generate_workspace_id(),
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
    row = (
        await session.execute(
            _base_query().where(Workspace.id == workspace_id).limit(1)
        )
    ).scalar_one_or_none()
    return row or default
