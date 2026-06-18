"""ToolRegistry 行为测试。"""

from __future__ import annotations

from locus_agent.tools.base import Tool, ToolResult
from locus_agent.tools.registry import ToolRegistry


async def _noop_handler(_args):
    return ToolResult(content="ok")


def _mcp_tool(name: str, workspace_id: str) -> Tool:
    return Tool(
        name=name,
        description="mcp",
        parameters={},
        handler=_noop_handler,
        category=f"mcp:{workspace_id}:server_a",
    )


def test_unregister_mcp_tools_outside_workspace():
    registry = ToolRegistry()
    ws_a = "ws_0123456789abcdef0123"
    ws_b = "ws_0123456789abcdef0124"
    registry.register(_mcp_tool("mcp__ws_a__s__t", ws_a))
    registry.register(_mcp_tool("mcp__ws_b__s__t", ws_b))
    removed = registry.unregister_mcp_tools_outside_workspace(ws_a)
    assert removed == 1
    assert registry.get("mcp__ws_a__s__t") is not None
    assert registry.get("mcp__ws_b__s__t") is None
