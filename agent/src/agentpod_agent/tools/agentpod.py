"""AgentPod 平台信息工具。"""

from __future__ import annotations

import os
from pathlib import Path

from agentpod_shared.settings_store import shared_skills_dir

from .base import Tool, ToolError, ToolResult, register_builtin

_DESCRIPTION = (
    "Query information about the AgentPod platform — what it is, its architecture, "
    "features (Skills, MCP, Memory, Artifacts, Workspaces, Scheduled Tasks, etc.), "
    "configuration, deployment, and usage. "
    "Use this tool when the user asks what AgentPod is, what capabilities the platform provides, "
    "how to set it up, or anything else about AgentPod itself. "
    "Do not use web_search or web_extract for questions about AgentPod."
)


def _resolve_readme_path() -> Path | None:
    override = os.environ.get("AGENTPOD_README_PATH", "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            return path

    repo_readme = Path(__file__).resolve().parents[4] / "README.md"
    if repo_readme.is_file():
        return repo_readme

    skills = shared_skills_dir()
    if skills is not None:
        bundled = skills.parent / "README.md"
        if bundled.is_file():
            return bundled

    return None


async def _handle(args: dict) -> ToolResult:
    readme = _resolve_readme_path()
    if readme is None:
        raise ToolError("AgentPod README not found.")
    content = readme.read_text(encoding="utf-8")
    return ToolResult(content=content)


register_builtin(
    Tool(
        name="agentpod",
        description=_DESCRIPTION,
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_handle,
    )
)
