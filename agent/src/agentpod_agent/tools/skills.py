"""skill_view / skill_manage 工具。"""

from __future__ import annotations

from typing import Any

from ..db import run_in_thread
from ..security import review_write
from ..skills import (
    Skill,
    create_skill,
    delete_skill,
    get_skill,
    list_skills,
    update_skill,
)
from .base import Tool, ToolError, ToolResult, register_builtin


async def _skill_view(args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name", "")).strip()

    if not name:
        skills = await run_in_thread(list_skills)
        if not skills:
            return ToolResult(content="(no skills)")
        lines = [f"- {s.name} [{s.source}]: {s.description}" for s in skills]
        return ToolResult(content="\n".join(lines))

    s = await run_in_thread(get_skill, name)
    if s is None:
        raise ToolError(f"skill not found: {name}")
    return ToolResult(
        content=f"# {s.name} [{s.source}]\n{s.description}\n\n{s.body}",
        metadata={"skill": s.to_dict()},
    )


async def _skill_manage(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "")).lower()
    name = str(args.get("name", "")).strip()
    if not name:
        raise ToolError("name is required")

    if action == "create":
        body = str(args.get("body", ""))
        verdict = await review_write(f"{args.get('description', '')}\n\n{body}", kind="skill")
        if not verdict.allowed:
            raise ToolError(f"skill write blocked by guard: {verdict.reason}")
        skill = Skill(
            name=name,
            description=str(args.get("description", "")),
            body=body,
            triggers=list(args.get("triggers", []) or []),
            source="private",
        )
        try:
            await run_in_thread(create_skill, skill)
        except FileExistsError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=f"skill '{name}' created")

    if action == "update":
        body = args.get("body")
        if body is not None:
            verdict = await review_write(str(body), kind="skill")
            if not verdict.allowed:
                raise ToolError(f"skill write blocked by guard: {verdict.reason}")
        try:
            await run_in_thread(
                update_skill,
                name,
                description=args.get("description"),
                body=body,
                triggers=args.get("triggers"),
            )
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=f"skill '{name}' updated")

    if action == "delete":
        ok = await run_in_thread(delete_skill, name)
        if not ok:
            raise ToolError(f"private skill not found: {name}")
        return ToolResult(content=f"skill '{name}' deleted")

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="skill_view",
        description="查看 Skill：name 为空时列出全部，给定 name 时返回正文。",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "default": ""}},
        },
        handler=_skill_view,
    )
)

register_builtin(
    Tool(
        name="skill_manage",
        description="管理私有 Skill：create / update / delete。公共 Skill 只读。",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "delete"]},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "body": {"type": "string"},
                "triggers": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["action", "name"],
        },
        handler=_skill_manage,
    )
)
