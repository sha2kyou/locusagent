"""skill_view / skill_manage 工具。"""

from __future__ import annotations

from typing import Any

import httpx

from ..core.write_origin import ORIGIN_AUTO_EXTRACT, ORIGIN_MANUAL, is_auto_extract_write
from ..db import run_in_thread
from ..security import review_write
from ..skills import (
    Skill,
    create_skill,
    delete_skill,
    format_skill_file_tree,
    get_skill,
    install_skill_from_url,
    list_skills,
    read_skill_file,
    update_skill,
)
from ..tool_settings import is_skill_enabled
from .args import pick_action, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


async def _skill_view(args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name", "")).strip()
    file_path = pick_str(args, "file_path", "path")

    if not name:
        skills = await run_in_thread(list_skills)
        skills = [s for s in skills if is_skill_enabled(s.name)]
        if not skills:
            return ToolResult(content="(no skills)")
        lines = []
        for s in skills:
            tags = [s.source]
            if s.origin == ORIGIN_AUTO_EXTRACT:
                tags.append("auto_extract")
            lines.append(f"- {s.name} [{', '.join(tags)}]: {s.description}")
        return ToolResult(content="\n".join(lines))

    if not is_skill_enabled(name):
        raise ToolError(f"skill disabled: {name}")
    s = await run_in_thread(get_skill, name)
    if s is None:
        raise ToolError(f"skill not found: {name}")

    if file_path:
        try:
            content = await run_in_thread(read_skill_file, name, file_path)
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        except IsADirectoryError as exc:
            raise ToolError(str(exc)) from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(
            content=f"# {name}/{file_path}\n\n{content}",
            metadata={"skill": name, "file_path": file_path},
        )

    origin_note = f", origin={s.origin}" if s.origin == ORIGIN_AUTO_EXTRACT else ""
    file_tree = await run_in_thread(format_skill_file_tree, name)
    return ToolResult(
        content=f"# {s.name} [{s.source}{origin_note}]\n{s.description}\n\n{s.body}{file_tree}",
        metadata={"skill": s.to_dict()},
    )


async def _skill_manage(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    name = pick_str(args, "name")
    if not name:
        raise ToolError("name is required")

    if action == "create":
        body = pick_str(args, "body")
        verdict = await review_write(f"{args.get('description', '')}\n\n{body}", kind="skill")
        if not verdict.allowed:
            raise ToolError(f"skill write blocked by guard: {verdict.reason}")
        skill = Skill(
            name=name,
            description=str(args.get("description", "")),
            body=body,
            source="private",
            origin=ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else ORIGIN_MANUAL,
        )
        try:
            await run_in_thread(create_skill, skill)
        except FileExistsError as exc:
            raise ToolError(str(exc)) from exc
        origin_label = " [auto_extract]" if skill.origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(content=f"skill '{name}' created{origin_label}")

    if action == "update":
        body = args.get("body")
        if body is not None:
            verdict = await review_write(str(body), kind="skill")
            if not verdict.allowed:
                raise ToolError(f"skill write blocked by guard: {verdict.reason}")
        write_origin = ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else None
        try:
            await run_in_thread(
                update_skill,
                name,
                description=args.get("description"),
                body=body,
                origin=write_origin,
            )
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        origin_label = " [auto_extract]" if write_origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(content=f"skill '{name}' updated{origin_label}")

    if action == "patch":
        old_string = pick_str(args, "old_string")
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
            write_origin = ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else None
            await run_in_thread(
                update_skill,
                name,
                description=None,
                body=patched,
                origin=write_origin,
            )
        except FileNotFoundError as exc:
            raise ToolError(str(exc)) from exc
        origin_label = " [auto_extract]" if write_origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(
            content=f"skill '{name}' patched ({count} match{'es' if count != 1 else ''}){origin_label}"
        )

    if action == "delete":
        ok = await run_in_thread(delete_skill, name)
        if not ok:
            raise ToolError(f"private skill not found: {name}")
        return ToolResult(content=f"skill '{name}' deleted")

    raise ToolError(f"unknown action: {action}")


async def _skill_install(args: dict[str, Any]) -> ToolResult:
    url = pick_str(args, "url", "source")
    if not url:
        raise ToolError("url is required")
    subpath = pick_str(args, "path", "subpath") or None
    overwrite = bool(args.get("overwrite", False))
    try:
        result = await run_in_thread(
            install_skill_from_url,
            url,
            subpath=subpath,
            overwrite=overwrite,
        )
    except FileExistsError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"download failed: {exc}") from exc
    return ToolResult(
        content=(
            f"skill '{result.name}' installed ({result.file_count} files)\n"
            f"description: {result.description or '(none)'}\n"
            f"path: {result.install_path}"
        ),
        metadata=result.to_dict(),
    )


register_builtin(
    Tool(
        name="skill_view",
        description=(
            "View skill content. Empty name lists summaries. "
            "Given name returns full SKILL.md; optional file_path loads a file under the skill directory "
            "(e.g. references/guide.md, scripts/run.sh)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": ""},
                "file_path": {
                    "type": "string",
                    "description": "Relative path within the skill directory. Alias: path.",
                },
                "path": {"type": "string", "description": "Alias for file_path."},
            },
        },
        handler=_skill_view,
    )
)

register_builtin(
    Tool(
        name="skill_manage",
        description=(
            "Manage private skills: create / update / patch / delete."
            "patch does targeted old_string/new_string replacement."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "patch", "delete"]},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "body": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["action", "name"],
        },
        handler=_skill_manage,
    )
)

register_builtin(
    Tool(
        name="skill_install",
        description=(
            "Install a skill from a URL into the current workspace skills/ directory "
            "(full directory with references/, scripts/, etc.). "
            "Supports GitHub repo/tree/blob links (github:owner/repo optional), zip archives, "
            "and direct SKILL.md URLs. Use path when the repo contains multiple skills."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "GitHub link, zip URL, or direct SKILL.md URL.",
                },
                "path": {
                    "type": "string",
                    "description": "Subpath within the repo/archive to the skill directory or SKILL.md.",
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": "Replace an already installed skill with the same name.",
                },
            },
            "required": ["url"],
        },
        handler=_skill_install,
    )
)
