"""Workspace management APIs (session auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth import AuthContext, require_session
from ..db import Workspace, get_session
from ..workspaces import (
    ensure_default_workspace,
    generate_workspace_id,
    normalize_workspace_description,
    normalize_workspace_name,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreateIn(BaseModel):
    name: str = Field(default="新工作区", min_length=1, max_length=25)
    description: str = Field(default="", max_length=200)


class WorkspaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=25)
    description: str | None = Field(default=None, max_length=200)


@router.get("")
async def list_workspaces(ctx: AuthContext = Depends(require_session)) -> dict:
    _ = ctx
    async with get_session() as session:
        default = await ensure_default_workspace(session)
        rows = (
            await session.execute(
                select(Workspace).order_by(Workspace.created_at.asc(), Workspace.id.asc())
            )
        ).scalars().all()
    return {
        "default_workspace_id": default.id,
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "is_default": bool(r.is_default),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
    }


@router.post("", status_code=201)
async def create_workspace(
    payload: WorkspaceCreateIn,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    name = normalize_workspace_name(payload.name)
    description = normalize_workspace_description(payload.description)
    async with get_session() as session:
        await ensure_default_workspace(session)
        row = Workspace(
            id=generate_workspace_id(),
            name=name,
            description=description,
        )
        while True:
            row.id = generate_workspace_id()
            exists = (
                await session.execute(select(Workspace.id).where(Workspace.id == row.id))
            ).first()
            if not exists:
                break
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return {
        "item": {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "is_default": bool(row.is_default),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    }


@router.post("/{workspace_id}/default")
async def set_default_workspace(
    workspace_id: str,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    async with get_session() as session:
        await ensure_default_workspace(session)
        row = (
            await session.execute(
                select(Workspace).where(Workspace.id == workspace_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")
        await session.execute(
            Workspace.__table__.update()
            .where(Workspace.is_default.is_(True))
            .values(is_default=False)
        )
        row.is_default = True
        await session.flush()
    return {"default_workspace_id": workspace_id}


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateIn,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    async with get_session() as session:
        await ensure_default_workspace(session)
        row = (
            await session.execute(
                select(Workspace).where(Workspace.id == workspace_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")
        if payload.name is None and payload.description is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="nothing to update")
        if payload.name is not None:
            row.name = normalize_workspace_name(payload.name)
        if payload.description is not None:
            row.description = normalize_workspace_description(payload.description)
        await session.flush()
        await session.refresh(row)
        return {
            "item": {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "is_default": bool(row.is_default),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        }


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    async with get_session() as session:
        await ensure_default_workspace(session)
        rows = (
            await session.execute(
                select(Workspace).order_by(Workspace.created_at.asc(), Workspace.id.asc())
            )
        ).scalars().all()
        target = next((r for r in rows if r.id == workspace_id), None)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")
        if target.is_default:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="default workspace cannot be deleted")
        if len(rows) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="at least one workspace required")
        await session.delete(target)
    return {"deleted": True}
