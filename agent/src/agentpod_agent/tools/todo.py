"""todo 工具：任务拆解与执行节点确认（agent 自行推进，无需用户确认）。"""

from __future__ import annotations

import json
from typing import Any

from ..core.run_context import get_chat_session_id
from ..todos.store import confirm_step, create_plan, get_plan, plan_to_json
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
        plan = await get_plan(session_id)
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
            "任务拆解与执行进度跟踪。由 agent 自行拆解步骤并在执行过程中确认节点状态，"
            "前端展示进度，无需用户点击确认。"
            "action=create：将复杂任务拆为 2–20 个有序步骤（每步需唯一 id 与 title，可选 detail）。"
            "会覆盖当前会话已有计划。"
            "action=confirm：更新某步骤状态——执行前 mark in_progress，完成后 mark done（可选 note 简述结果）；"
            "无法并行两个 in_progress 步骤。"
            "action=view：读取当前计划。"
            "适用：多步任务（通常 3 步及以上，或 intent 评分≥3）。简单一问一答无需调用。"
            "流程：create → 对当前步骤 confirm(in_progress) → 执行工具/产出 → confirm(done) → 下一步。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "confirm", "view"],
                    "description": "create=拆解任务；confirm=确认节点进度；view=查看计划",
                },
                "title": {
                    "type": "string",
                    "description": "create 时必需：任务总标题",
                },
                "steps": {
                    "type": "array",
                    "description": "create 时必需：步骤列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "步骤唯一 id"},
                            "title": {"type": "string", "description": "步骤标题"},
                            "detail": {"type": "string", "description": "可选说明"},
                        },
                        "required": ["id", "title"],
                    },
                },
                "step_id": {
                    "type": "string",
                    "description": "confirm 时必需：要更新的步骤 id",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "skipped"],
                    "description": "confirm 时必需：步骤新状态",
                },
                "note": {
                    "type": "string",
                    "description": "confirm 为 done 时可选：本步结果摘要",
                },
            },
            "required": ["action"],
        },
        handler=_todo,
    )
)
