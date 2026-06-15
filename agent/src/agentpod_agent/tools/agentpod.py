"""AgentPod 平台信息工具。"""

from __future__ import annotations

import os
from pathlib import Path

from agentpod_shared.settings_store import shared_skills_dir

from .base import Tool, ToolError, ToolResult, register_builtin

_DESCRIPTION = (
    "Load the AgentPod agent capability guide: what the platform can do for users, "
    "which tools you have, delivery conventions, UI handoffs, and user-facing troubleshooting. "
    "Use when the user asks about AgentPod itself, what you can help with on this platform, "
    "or how to guide them through settings, workspaces, logs, scheduled tasks, etc. "
    "This is not source code or system architecture — do not use web_search for AgentPod questions."
)


def _resolve_agent_doc_path() -> Path | None:
    override = os.environ.get("AGENTPOD_AGENT_DOC_PATH", "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            return path

    override_readme = os.environ.get("AGENTPOD_README_PATH", "").strip()
    if override_readme:
        path = Path(override_readme)
        if path.is_file():
            return path

    repo_root = Path(__file__).resolve().parents[4]
    for name in ("AGENT.md", "README.md"):
        candidate = repo_root / name
        if candidate.is_file():
            return candidate

    skills = shared_skills_dir()
    if skills is not None:
        for name in ("AGENT.md", "README.md"):
            bundled = skills.parent / name
            if bundled.is_file():
                return bundled

    return None


async def _handle(args: dict) -> ToolResult:
    doc = _resolve_agent_doc_path()
    if doc is None:
        raise ToolError("AgentPod agent capability doc not found.")
    content = doc.read_text(encoding="utf-8")
    return ToolResult(content=content)


register_builtin(
    Tool(
        name="agentpod",
        description=_DESCRIPTION,
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_handle,
    )
)
