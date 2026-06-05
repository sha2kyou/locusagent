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
            "任务拆解与执行进度跟踪。由助手自行拆解步骤并在执行过程中确认节点状态；"
            "前端展示进度，无需用户点击确认。\n\n"
            f"{TODO_TOOL_USAGE_GUIDANCE}\n\n"
            "操作说明：\n"
            "- action 取 create：将复杂任务拆为二至二十个有序步骤（每步需唯一步骤标识与标题，可选说明）。"
            "会覆盖当前会话已有计划；新话题开始后必须先创建计划，不可继续确认旧计划。\n"
            "- action 取 confirm：更新某步骤状态——执行前取进行中，完成后取已完成（可选备注）；"
            "不可并行两个进行中步骤。\n"
            "- action 取 view：读取当前计划。\n"
            "推荐流程：创建计划 → 标记进行中 → 执行工具 → 标记已完成 → 下一步。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "confirm", "view"],
                    "description": "create 拆解任务；confirm 确认节点进度；view 查看计划",
                },
                "title": {
                    "type": "string",
                    "description": "创建计划时必需：任务总标题",
                },
                "steps": {
                    "type": "array",
                    "description": "创建计划时必需：步骤列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "步骤唯一标识"},
                            "title": {"type": "string", "description": "步骤标题"},
                            "detail": {"type": "string", "description": "可选说明文字"},
                        },
                        "required": ["id", "title"],
                    },
                },
                "step_id": {
                    "type": "string",
                    "description": "确认进度时必需：要更新的步骤标识",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "skipped"],
                    "description": "确认进度时必需：步骤新状态，取值见上方枚举",
                },
                "note": {
                    "type": "string",
                    "description": "标记已完成时可选：本步结果摘要",
                },
            },
            "required": ["action"],
        },
        handler=_todo,
    )
)
