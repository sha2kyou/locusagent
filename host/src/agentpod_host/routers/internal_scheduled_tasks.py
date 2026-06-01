"""Agent 容器内部回调：定时任务 CRUD。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..db import User, get_session
from ..scheduled_tasks import create_task, delete_task, get_task, list_tasks, update_task
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/internal/scheduled-tasks", tags=["internal-scheduled-tasks"])


class ScheduledTaskCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    prompt: str = Field(..., min_length=1, max_length=20000)
    schedule_kind: Literal["once", "cron"]
    enabled: bool = True
    notify: bool = True
    cron_expr: str | None = Field(default=None, max_length=120)
    run_at: str | None = Field(default=None, max_length=32)


class ScheduledTaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, min_length=1, max_length=20000)
    enabled: bool | None = None
    notify: bool | None = None
    cron_expr: str | None = Field(default=None, max_length=120)
    run_at: str | None = Field(default=None, max_length=32)


async def _workspace_for_request(request: Request, user_id: int) -> str:
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            user_id=user_id,
            workspace_id=requested_workspace_id(request),
        )
        return ws.id


@router.get("")
async def agent_list_scheduled_tasks(
    request: Request,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    items = await list_tasks(user.id, workspace_id=workspace_id)
    return {"items": items}


@router.post("", status_code=201)
async def agent_create_scheduled_task(
    request: Request,
    payload: ScheduledTaskCreateIn,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    try:
        item = await create_task(
            user.id,
            workspace_id=workspace_id,
            title=payload.title,
            prompt=payload.prompt,
            schedule_kind=payload.schedule_kind,
            enabled=payload.enabled,
            notify=payload.notify,
            cron_expr=payload.cron_expr,
            run_at_local=payload.run_at,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"item": item}


@router.put("/{task_id}")
async def agent_update_scheduled_task(
    request: Request,
    task_id: int,
    payload: ScheduledTaskUpdateIn,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    try:
        item = await update_task(
            user.id,
            task_id,
            workspace_id=workspace_id,
            title=payload.title,
            prompt=payload.prompt,
            enabled=payload.enabled,
            notify=payload.notify,
            cron_expr=payload.cron_expr,
            run_at_local=payload.run_at,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return {"item": item}


@router.delete("/{task_id}")
async def agent_delete_scheduled_task(
    request: Request,
    task_id: int,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    ok = await delete_task(user.id, task_id, workspace_id=workspace_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return {"deleted": True}


@router.get("/{task_id}")
async def agent_read_scheduled_task(
    request: Request,
    task_id: int,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    item = await get_task(user.id, task_id, workspace_id=workspace_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return {"item": item}
