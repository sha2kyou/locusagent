"""用户定时任务 CRUD。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from locus_shared.activity_log import record_activity

from ..auth import AuthContext, require_session
from ..scheduled_tasks import create_task, delete_task, get_task, list_tasks, update_task
from ..scheduled_tasks.executor import trigger_task_run
from ..db import get_session
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


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


async def _workspace_for_request(request: Request) -> str:
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            workspace_id=requested_workspace_id(request),
        )
        return ws.id


@router.get("")
async def list_scheduled_tasks(request: Request, ctx: AuthContext = Depends(require_session)) -> dict:
    _ = ctx
    workspace_id = await _workspace_for_request(request)
    items = await list_tasks(workspace_id=workspace_id)
    return {"items": items}


@router.post("", status_code=201)
async def create_scheduled_task(
    request: Request,
    payload: ScheduledTaskCreateIn,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    workspace_id = await _workspace_for_request(request)
    try:
        item = await create_task(
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
    record_activity(
        "scheduled",
        "create",
        f"已创建定时任务「{item['title']}」",
        workspace_id=workspace_id,
        detail={"task_id": item["id"], "schedule_kind": payload.schedule_kind},
    )
    return {"item": item}


@router.put("/{task_id}")
async def update_scheduled_task(
    request: Request,
    task_id: int,
    payload: ScheduledTaskUpdateIn,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    workspace_id = await _workspace_for_request(request)
    try:
        item = await update_task(
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
    record_activity(
        "scheduled",
        "update",
        f"已更新定时任务「{item['title']}」",
        workspace_id=workspace_id,
        detail={"task_id": task_id},
    )
    return {"item": item}


@router.delete("/{task_id}")
async def delete_scheduled_task(
    request: Request,
    task_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    workspace_id = await _workspace_for_request(request)
    ok = await delete_task(task_id, workspace_id=workspace_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    record_activity("scheduled", "delete", f"已删除定时任务 #{task_id}", workspace_id=workspace_id)
    return {"deleted": True}


@router.post("/{task_id}/run")
async def run_scheduled_task_now(
    request: Request,
    task_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    workspace_id = await _workspace_for_request(request)
    try:
        item = await trigger_task_run(task_id, workspace_id=workspace_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    record_activity(
        "scheduled",
        "run",
        f"已手动运行定时任务「{item['title']}」",
        workspace_id=workspace_id,
        detail={"task_id": task_id},
    )
    return {"item": item}


@router.get("/{task_id}")
async def read_scheduled_task(
    request: Request,
    task_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    workspace_id = await _workspace_for_request(request)
    item = await get_task(task_id, workspace_id=workspace_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return {"item": item}
