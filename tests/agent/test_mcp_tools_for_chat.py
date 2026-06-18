"""MCP 工具注入 registry 测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from locus_agent.tools import registry as tool_registry
from locus_agent.workspace import mcp_tool_category, mcp_tool_full_name, set_workspace_id
from locus_agent.workspace_runtime import ensure_mcp_tools_for_chat


@pytest.mark.asyncio
async def test_ensure_mcp_tools_for_chat_publishes_when_sessions_exist() -> None:
    wid = "ws_b5c9f41f1254b9b780b9"
    set_workspace_id(wid)
    server = "sidefy"
    full_name = mcp_tool_full_name(server, "list_today_events", wid)
    category = mcp_tool_category(server, wid)

    mgr = MagicMock()
    mgr._sessions = {server: object()}
    mgr._tool_catalog = {
        server: [
            {
                "name": "list_today_events",
                "full_name": full_name,
                "description": "sidefy tool",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
    }
    mgr.publish_tools_to_registry = AsyncMock(
        side_effect=lambda: tool_registry.register(
            __import__("locus_agent.tools.base", fromlist=["Tool"]).Tool(
                name=full_name,
                description="sidefy tool",
                parameters={"type": "object", "properties": {}},
                handler=AsyncMock(),
                enabled=True,
                category=category,
            )
        )
    )

    with patch("locus_agent.workspace_runtime.ensure_workspace_context", new=AsyncMock()):
        with patch("locus_agent.mcp_.client.ensure_mcp_manager", new=AsyncMock(return_value=mgr)):
            await ensure_mcp_tools_for_chat(wid)

    mgr.publish_tools_to_registry.assert_awaited_once()
    names = {t.name for t in tool_registry.list(workspace_id=wid)}
    assert full_name in names


@pytest.mark.asyncio
async def test_publish_tools_uses_catalog_without_list_tools() -> None:
    from locus_agent.mcp_.client import MCPManager

    wid = "ws_b5c9f41f1254b9b780b9"
    set_workspace_id(wid)
    server = "sidefy"
    full_name = mcp_tool_full_name(server, "ping", wid)

    mgr = MCPManager(wid)
    mgr._sessions[server] = object()
    mgr._tool_catalog[server] = [
        {
            "name": "ping",
            "full_name": full_name,
            "description": "ping tool",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]

    session = MagicMock()
    session.list_tools = AsyncMock(side_effect=TimeoutError("should not be called"))

    await mgr.publish_tools_to_registry()

    session.list_tools.assert_not_called()
    names = {t.name for t in tool_registry.list(workspace_id=wid)}
    assert full_name in names
