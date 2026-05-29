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
from ..tool_settings import is_skill_enabled
from .base import Tool, ToolError, ToolResult, register_builtin


async def _skill_view(args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name", "")).strip()

    if not name:
        skills = await run_in_thread(list_skills)
        skills = [s for s in skills if is_skill_enabled(s.name)]
        if not skills:
            return ToolResult(content="(no skills)")
        lines = [f"- {s.name} [{s.source}]: {s.description}" for s in skills]
        return ToolResult(content="\n".join(lines))

    if not is_skill_enabled(name):
        raise ToolError(f"skill disabled: {name}")
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

    if action in {"update", "edit"}:
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

    if action == "patch":
        old_string = str(args.get("old_string", ""))
        new_string = args.get("new_string")
        replace_all = bool(args.get("replace_all", False))
        if not old_string:
            raise ToolError("old_string is required")
        if new_string is None:
            raise ToolError("new_string is required (use empty string to delete)")
        current = await run_in_thread(get_skill, name)
        if current is None:
            raise ToolError(f"skill not found: {name}")
        body = str(current.body)
        if replace_all:
            count = body.count(old_string)
            if count < 1:
                raise ToolError("old_string not found")
            patched = body.replace(old_string, str(new_string))
        else:
            count = body.count(old_string)
            if count < 1:
                raise ToolError("old_string not found")
            if count > 1:
                raise ToolError("old_string matched multiple sections; provide more context or set replace_all=true")
            patched = body.replace(old_string, str(new_string), 1)
        verdict = await review_write(str(patched), kind="skill")
        if not verdict.allowed:
            raise ToolError(f"skill write blocked by guard: {verdict.reason}")
        try:
            await run_in_thread(
                update_skill,
                name,
                description=None,
                body=patched,
                triggers=None,
            )
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=f"skill '{name}' patched ({count} match{'es' if count != 1 else ''})")

    if action == "delete":
        ok = await run_in_thread(delete_skill, name)
        if not ok:
            raise ToolError(f"private skill not found: {name}")
        return ToolResult(content=f"skill '{name}' deleted")

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="skill_view",
        description="查看技能内容。name 为空时列出技能摘要；给定 name 时返回完整 SKILL.md 内容。",
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
        description=(
            "管理私有技能：create / edit / patch / delete。"
            "其中 patch 用于按 old_string/new_string 做定点替换。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "edit", "patch", "delete", "update"]},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "body": {"type": "string"},
                "triggers": {"type": "array", "items": {"type": "string"}},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["action", "name"],
        },
        handler=_skill_manage,
    )
)
