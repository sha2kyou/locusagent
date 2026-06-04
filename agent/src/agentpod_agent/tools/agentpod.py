"""AgentPod 平台信息工具。"""

from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolError, ToolResult, register_builtin

_README_PATH = Path("/app/README.md")

_DESCRIPTION = (
    "Query information about the AgentPod platform — what it is, its architecture, "
    "features (Skills, MCP, Memory, Artifacts, Workspaces, Scheduled Tasks, etc.), "
    "configuration, deployment, and usage. "
    "Use this tool when the user asks what AgentPod is, what capabilities the platform provides, "
    "how to set it up, or anything else about AgentPod itself. "
    "Do not use web_search or web_extract for questions about AgentPod."
)


async def _handle(args: dict) -> ToolResult:
    if not _README_PATH.exists():
        raise ToolError("AgentPod README not found in container.")
    content = _README_PATH.read_text(encoding="utf-8")
    return ToolResult(content=content)


register_builtin(
    Tool(
        name="agentpod",
        description=_DESCRIPTION,
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_handle,
    )
)
