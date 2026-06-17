"""hook_view / hook_manage：工作区级 post_user_submit hook 管理。"""

from __future__ import annotations

from typing import Any

from ..db import run_in_thread
from ..hooks import list_post_user_submit_hooks
from ..hooks.loader import reload_workspace_hooks
from ..hooks.store import (
    create_hook,
    delete_hook,
    list_hooks,
    read_hook,
    update_hook,
)
from ..security import review_write
from ..tool_settings import is_hook_enabled, set_hook_enabled
from .args import pick_action, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


async def _hook_view(args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name", "")).strip()
    if not name:
        hooks = await run_in_thread(list_hooks)
        if not hooks:
            return ToolResult(content="(no hooks)")
        active = {entry["hook_name"] for entry in list_post_user_submit_hooks() if entry["hook_name"]}
        lines = []
        for hook_name in hooks:
            enabled = "enabled" if is_hook_enabled(hook_name) else "disabled"
            loaded = "loaded" if hook_name in active else "not_loaded"
            lines.append(f"- {hook_name} [{enabled}, {loaded}]")
        return ToolResult(content="\n".join(lines))

    if not is_hook_enabled(name):
        raise ToolError(f"hook disabled: {name}")
    try:
        content = await run_in_thread(read_hook, name)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    return ToolResult(content=f"# hook: {name}\n\n{content}", metadata={"hook": name})


async def _hook_manage(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    name = pick_str(args, "name")
    if not name:
        raise ToolError("name is required")

    if action == "create":
        body = args.get("body")
        if body is not None:
            verdict = await review_write(str(body), kind="skill")
            if not verdict.allowed:
                raise ToolError(f"hook write blocked by guard: {verdict.reason}")
        try:
            content = await run_in_thread(create_hook, name, body)
        except FileExistsError as exc:
            raise ToolError(str(exc)) from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        await run_in_thread(reload_workspace_hooks)
        return ToolResult(content=f"hook '{name}' created\npath: hooks/{name}/hook.py\n\n{content}")

    if action == "update":
        body = pick_str(args, "body")
        verdict = await review_write(body, kind="skill")
        if not verdict.allowed:
            raise ToolError(f"hook write blocked by guard: {verdict.reason}")
        try:
            content = await run_in_thread(update_hook, name, body)
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        await run_in_thread(reload_workspace_hooks)
        return ToolResult(content=f"hook '{name}' updated\n\n{content}")

    if action == "patch":
        old_string = pick_str(args, "old_string")
        new_string = args.get("new_string")
        replace_all = bool(args.get("replace_all", False))
        if not old_string:
            raise ToolError("old_string is required")
        if new_string is None:
            raise ToolError("new_string is required (use empty string to delete)")
        try:
            current = await run_in_thread(read_hook, name)
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        if replace_all:
            count = current.count(old_string)
            if count < 1:
                raise ToolError("old_string not found")
            patched = current.replace(old_string, str(new_string))
        else:
            count = current.count(old_string)
            if count < 1:
                raise ToolError("old_string not found")
            if count > 1:
                raise ToolError("old_string matched multiple sections; provide more context or set replace_all=true")
            patched = current.replace(old_string, str(new_string), 1)
        verdict = await review_write(patched, kind="skill")
        if not verdict.allowed:
            raise ToolError(f"hook write blocked by guard: {verdict.reason}")
        try:
            content = await run_in_thread(update_hook, name, patched)
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        await run_in_thread(reload_workspace_hooks)
        return ToolResult(
            content=f"hook '{name}' patched ({count} match{'es' if count != 1 else ''})\n\n{content}"
        )

    if action == "delete":
        ok = await run_in_thread(delete_hook, name)
        if not ok:
            raise ToolError(f"hook not found: {name}")
        await run_in_thread(reload_workspace_hooks)
        return ToolResult(content=f"hook '{name}' deleted")

    if action == "enable":
        await run_in_thread(set_hook_enabled, name, True)
        return ToolResult(content=f"hook '{name}' enabled")

    if action == "disable":
        await run_in_thread(set_hook_enabled, name, False)
        return ToolResult(content=f"hook '{name}' disabled")

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="hook_view",
        description=(
            "View workspace lifecycle hooks. Empty name lists hooks under hooks/<name>/hook.py. "
            "Given name returns hook.py source. Hooks run on post_user_submit (after user message accepted)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": ""},
            },
        },
        handler=_hook_view,
    )
)

register_builtin(
    Tool(
        name="hook_manage",
        description=(
            "Manage workspace hooks: create / update / patch / delete / enable / disable hook.py under hooks/<name>/. "
            "Each hook must define register(ctx) and may call ctx.register_post_user_submit(callback)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "patch", "delete", "enable", "disable"]},
                "name": {"type": "string"},
                "body": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["action", "name"],
        },
        handler=_hook_manage,
    )
)
