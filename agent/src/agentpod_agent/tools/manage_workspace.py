"""manage_workspace：工作区环境摘要（只读）。

返回技能、MCP、记忆、环境变量、定时任务、产物的条数与各自最近 5 条数据。
MCP 的增删改操作走 mcp_manage；重连/刷新工具列表走 mcp_refresh。
"""

from __future__ import annotations

from typing import Any

from ..workspace_summary import build_workspace_summary
from .base import Tool, ToolResult, register_builtin


async def _manage_workspace(_args: dict[str, Any]) -> ToolResult:
    content, meta = await build_workspace_summary()
    return ToolResult(content=content, metadata=meta)


register_builtin(
    Tool(
        name="manage_workspace",
        description=(
            "工作区环境摘要（只读）。"
            "返回技能、MCP、记忆、环境变量、定时任务、产物的条数与各自最近 5 条数据。"
            "MCP 的增删改请用 mcp_manage；重连/刷新工具列表请用 mcp_refresh；其他资源 CRUD 走对应专用工具。"
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_manage_workspace,
    )
)
