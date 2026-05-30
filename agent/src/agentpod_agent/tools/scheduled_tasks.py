"""scheduled_task_view / scheduled_task_manage 工具。"""

from __future__ import annotations

from typing import Any

from ..host_scheduled_tasks import (
    HostScheduledTasksError,
    create_scheduled_task,
    delete_scheduled_task,
    list_scheduled_tasks,
    update_scheduled_task,
)
from ..security import review_write
from .base import Tool, ToolError, ToolResult, register_builtin


def _clamp_int(v: Any, *, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(min_v, min(max_v, n))


def _task_line(item: dict[str, Any]) -> str:
    tid = item.get("id")
    title = str(item.get("title") or "").strip() or "(untitled)"
    schedule_kind = str(item.get("schedule_kind") or "")
    trigger = str(item.get("run_at") or item.get("cron_expr") or "—")
    enabled = "enabled" if bool(item.get("enabled")) else "disabled"
    status = str(item.get("last_run_status") or "idle")
    return f"#{tid} [{schedule_kind}] {title} | {trigger} | {enabled} | {status}"


async def _scheduled_task_view(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip().lower()
    limit = _clamp_int(args.get("limit"), default=20, min_v=1, max_v=100)
    include_completed = bool(args.get("include_completed", False))
    include_disabled = bool(args.get("include_disabled", True))

    try:
        items = await list_scheduled_tasks()
    except HostScheduledTasksError as exc:
        raise ToolError(str(exc)) from exc

    def _match(item: dict[str, Any]) -> bool:
        if not include_completed and item.get("completed_at"):
            return False
        if not include_disabled and not bool(item.get("enabled")):
            return False
        if not query:
            return True
        haystack = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("prompt") or ""),
                str(item.get("schedule_kind") or ""),
                str(item.get("cron_expr") or ""),
                str(item.get("run_at") or ""),
                str(item.get("last_run_status") or ""),
            ]
        ).lower()
        return query in haystack

    matched = [it for it in items if _match(it)]
    sliced = matched[:limit]
    if not sliced:
        return ToolResult(content="(no scheduled task hits)", metadata={"items": [], "query": query})
    return ToolResult(
        content="\n".join(_task_line(it) for it in sliced),
        metadata={"items": sliced, "query": query, "total": len(matched)},
    )


async def _scheduled_task_manage(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "")).strip().lower()
    if action in {"edit"}:
        action = "update"
    if action in {"remove"}:
        action = "delete"

    if action == "create":
        title = str(args.get("title", "")).strip()
        prompt = str(args.get("prompt", "")).strip()
        schedule_kind = str(args.get("schedule_kind", "")).strip().lower()
        enabled = bool(args.get("enabled", True))
        notify = bool(args.get("notify", True))
        cron_expr = args.get("cron_expr")
        run_at = args.get("run_at")
        if not title:
            raise ToolError("title is required")
        if not prompt:
            raise ToolError("prompt is required")
        if schedule_kind not in {"once", "cron"}:
            raise ToolError("schedule_kind must be once or cron")
        verdict = await review_write(prompt, kind="scheduled_task")
        if not verdict.allowed:
            raise ToolError(f"scheduled task prompt blocked by guard: {verdict.reason}")
        payload: dict[str, Any] = {
            "title": title,
            "prompt": prompt,
            "schedule_kind": schedule_kind,
            "enabled": enabled,
            "notify": notify,
            "cron_expr": str(cron_expr).strip() if cron_expr is not None else None,
            "run_at": str(run_at).strip() if run_at is not None else None,
        }
        try:
            item = await create_scheduled_task(payload)
        except HostScheduledTasksError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=f"scheduled_task#{item.get('id')} created", metadata={"item": item})

    if action == "update":
        task_id = int(args.get("id", 0) or 0)
        if not task_id:
            raise ToolError("id is required for update")
        payload: dict[str, Any] = {}
        for field in ("title", "enabled", "notify", "cron_expr", "run_at"):
            if field in args:
                payload[field] = args.get(field)
        if "prompt" in args:
            prompt = str(args.get("prompt", "")).strip()
            if not prompt:
                raise ToolError("prompt cannot be empty")
            verdict = await review_write(prompt, kind="scheduled_task")
            if not verdict.allowed:
                raise ToolError(f"scheduled task prompt blocked by guard: {verdict.reason}")
            payload["prompt"] = prompt
        if not payload:
            raise ToolError("no fields to update")
        if "title" in payload:
            payload["title"] = str(payload["title"]).strip()
        if "cron_expr" in payload and payload["cron_expr"] is not None:
            payload["cron_expr"] = str(payload["cron_expr"]).strip()
        if "run_at" in payload and payload["run_at"] is not None:
            payload["run_at"] = str(payload["run_at"]).strip()
        try:
            item = await update_scheduled_task(task_id, payload)
        except HostScheduledTasksError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=f"scheduled_task#{item.get('id')} updated", metadata={"item": item})

    if action == "delete":
        task_id = int(args.get("id", 0) or 0)
        if not task_id:
            raise ToolError("id is required for delete")
        try:
            ok = await delete_scheduled_task(task_id)
        except HostScheduledTasksError as exc:
            raise ToolError(str(exc)) from exc
        if not ok:
            raise ToolError(f"scheduled_task#{task_id} not found")
        return ToolResult(content=f"scheduled_task#{task_id} deleted")

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="scheduled_task_view",
        description="检索定时任务。可按 query 搜索标题/提示词/Cron/状态，返回任务列表与关键字段。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 20},
                "include_completed": {"type": "boolean", "default": False},
                "include_disabled": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
        handler=_scheduled_task_view,
    )
)


register_builtin(
    Tool(
        name="scheduled_task_manage",
        description="管理定时任务：create / update / delete。",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "delete", "edit", "remove"]},
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "prompt": {"type": "string"},
                "schedule_kind": {"type": "string", "enum": ["once", "cron"]},
                "enabled": {"type": "boolean"},
                "notify": {"type": "boolean"},
                "cron_expr": {"type": "string"},
                "run_at": {"type": "string"},
            },
            "required": ["action"],
        },
        handler=_scheduled_task_manage,
    )
)
