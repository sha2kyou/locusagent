"""todo 工具：任务拆解与执行节点确认（agent 自行推进，无需用户确认）。"""

from __future__ import annotations

import json
from typing import Any

from ..core.run_context import get_chat_session_id
from ..todos.intent import TODO_TOOL_USAGE_GUIDANCE
from ..todos.store import confirm_step, create_plan, get_active_plan, plan_to_json
from .args import pick_action, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


def is_todo_result(content: str) -> bool:
    """工具返回是否为可渲染的任务进度 JSON。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    if "plan" in data and data.get("plan") is None:
        return False
    steps = data.get("steps")
    return isinstance(data.get("plan_id"), str) and isinstance(steps, list) and len(steps) >= 2


async def _todo(args: dict[str, Any]) -> ToolResult:
    session_id = get_chat_session_id()
    if not session_id:
        raise ToolError("todo requires an active chat session")

    action = pick_action(args, default="view")
    if action == "view":
        plan = await get_active_plan(session_id)
        return ToolResult(content=plan_to_json(plan), metadata={"todo": True})

    if action == "create":
        title = pick_str(args, "title")
        if not title:
            raise ToolError("title is required for create")
        steps = args.get("steps")
        try:
            plan = await create_plan(session_id, title=title, steps=steps or [])
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=plan_to_json(plan), metadata={"todo": True})

    if action == "confirm":
        step_id = pick_str(args, "step_id", "id")
        status = pick_str(args, "status")
        note = pick_str(args, "note")
        if not step_id:
            raise ToolError("step_id is required for confirm")
        if not status:
            raise ToolError("status is required for confirm")
        try:
            plan = await confirm_step(session_id, step_id=step_id, status=status, note=note)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=plan_to_json(plan), metadata={"todo": True})

    raise ToolError("action must be one of: create, confirm, view")


register_builtin(
    Tool(
        name="todo",
        description=(
            "Task breakdown and execution progress tracking. The assistant breaks down steps and confirms status during execution;"
            "The UI shows progress; the user does not click to confirm.\n\n"
            f"{TODO_TOOL_USAGE_GUIDANCE}\n\n"
            "Operations:\n"
            "- action=create: split a complex task into 2–20 ordered steps (unique step id and title each, optional detail)."
            "Overwrites the current session plan; after a new topic, create a plan first—do not confirm an old plan.\n"
            "- action=confirm: update a step— in_progress before work, done after (optional note);"
            "Do not have two in_progress steps.\n"
            "- action=view: read the current plan.\n"
            "Recommended: create plan → mark in_progress → run tools → mark done → next step."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "confirm", "view"],
                    "description": "create=break down; confirm=update step; view=read plan",
                },
                "title": {
                    "type": "string",
                    "description": "Required for create: overall task title",
                },
                "steps": {
                    "type": "array",
                    "description": "Required for create: step list",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique step id"},
                            "title": {"type": "string", "description": "Step title"},
                            "detail": {"type": "string", "description": "Optional detail"},
                        },
                        "required": ["id", "title"],
                    },
                },
                "step_id": {
                    "type": "string",
                    "description": "Required for confirm: step id to update",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "skipped"],
                    "description": "Required for confirm: new step status (see enum)",
                },
                "note": {
                    "type": "string",
                    "description": "Optional when marking done: step result summary",
                },
            },
            "required": ["action"],
        },
        handler=_todo,
    )
)
