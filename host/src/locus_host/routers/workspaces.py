"""Workspace management APIs (session auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth import AuthContext, require_session
from ..db import Workspace, get_session
from agentpod_shared.workspace_ids import generate_workspace_id
from agentpod_shared.activity_log import record_activity
from ..workspaces import (
    copy_mcp_oauth_credentials,
    copy_workspace_on_disk,
    delete_workspace_on_disk,
    ensure_default_workspace,
    normalize_workspace_description,
    normalize_workspace_name,
    suggest_workspace_copy_name,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreateIn(BaseModel):
    name: str = Field(default="新工作区", min_length=1, max_length=25)
    description: str = Field(default="", max_length=200)


class WorkspaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=25)
    description: str | None = Field(default=None, max_length=200)


class WorkspaceCopyIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=25)


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
    record_activity("workspace", "create", f"已创建工作区「{row.name}」", workspace_id=row.id)
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
    record_activity("workspace", "default", f"已切换默认工作区", workspace_id=workspace_id)
    return {"default_workspace_id": workspace_id}


@router.post("/{workspace_id}/copy", status_code=201)
async def copy_workspace(
    workspace_id: str,
    payload: WorkspaceCopyIn | None = None,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    body = payload or WorkspaceCopyIn()
    async with get_session() as session:
        await ensure_default_workspace(session)
        source = (
            await session.execute(select(Workspace).where(Workspace.id == workspace_id))
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace not found")

        new_id = generate_workspace_id()
        while True:
            exists = (
                await session.execute(select(Workspace.id).where(Workspace.id == new_id))
            ).first()
            if not exists:
                break
            new_id = generate_workspace_id()

        name = (
            normalize_workspace_name(body.name)
            if body.name
            else suggest_workspace_copy_name(source.name)
        )
        try:
            copy_workspace_on_disk(source.id, new_id)
        except FileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="workspace has no agent data yet",
            ) from exc
        except FileExistsError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="target path exists") from exc

        row = Workspace(
            id=new_id,
            name=name,
            description=source.description,
            is_default=False,
        )
        session.add(row)
        await session.flush()
        await copy_mcp_oauth_credentials(session, source_id=source.id, target_id=new_id)
        await session.refresh(row)

    record_activity(
        "workspace",
        "copy",
        f"已复制工作区「{source.name}」→「{row.name}」",
        workspace_id=row.id,
    )
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
        record_activity("workspace", "update", f"已更新工作区「{row.name}」", workspace_id=row.id)
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
        await session.flush()
    try:
        delete_workspace_on_disk(workspace_id)
    except OSError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to remove workspace data",
        ) from exc
    record_activity("workspace", "delete", f"已删除工作区", workspace_id=workspace_id)
    return {"deleted": True}
