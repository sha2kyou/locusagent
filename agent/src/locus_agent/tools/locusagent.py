"""Locus Agent 平台信息工具。"""

from __future__ import annotations

import os
from pathlib import Path

from locus_shared.settings_store import shared_skills_dir

from .base import Tool, ToolError, ToolResult, register_builtin

_DESCRIPTION = (
    "Load the Locus Agent agent capability guide: what the platform can do for users, "
    "which tools you have, delivery conventions, UI handoffs, and user-facing troubleshooting. "
    "Use when the user asks about Locus Agent itself, what you can help with on this platform, "
    "or how to guide them through settings, workspaces, logs, scheduled tasks, etc. "
    "This is not source code or system architecture — do not use web_search for Locus Agent questions."
)


def _resolve_agent_doc_path() -> Path | None:
    override = os.environ.get("LOCUSAGENT_AGENT_DOC_PATH", "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            return path

    repo_root = Path(__file__).resolve().parents[4]
    doc = repo_root / "docs" / "LOCUSAGENT.md"
    if doc.is_file():
        return doc

    skills = shared_skills_dir()
    if skills is not None:
        bundled = skills.parent / "LOCUSAGENT.md"
        if bundled.is_file():
            return bundled

    override_readme = os.environ.get("LOCUSAGENT_README_PATH", "").strip()
    if override_readme:
        path = Path(override_readme)
        if path.is_file():
            return path

    readme = repo_root / "README.md"
    if readme.is_file():
        return readme

    return None


async def _handle(args: dict) -> ToolResult:
    doc = _resolve_agent_doc_path()
    if doc is None:
        raise ToolError("Locus Agent agent capability doc not found.")
    content = doc.read_text(encoding="utf-8")
    return ToolResult(content=content)


register_builtin(
    Tool(
        name="locusagent",
        description=_DESCRIPTION,
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_handle,
    )
)
