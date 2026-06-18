"""run_in_thread 应保留 ContextVar（如 workspace_id）。"""

from __future__ import annotations

import pytest

from locus_agent.db import run_in_thread
from locus_agent.mcp_.config import add_mcp_server, get_mcp_server, list_mcp_servers
from locus_agent.workspace import get_workspace_id, set_workspace_id

WS_A = "ws_0123456789abcdef0123"
WS_B = "ws_0123456789abcdef0124"


@pytest.mark.asyncio
async def test_run_in_thread_preserves_workspace_context() -> None:
    set_workspace_id(WS_A)

    def _read() -> str:
        return get_workspace_id()

    assert await run_in_thread(_read) == WS_A


@pytest.mark.asyncio
async def test_mcp_config_reads_active_workspace_in_thread(tmp_path, monkeypatch) -> None:
    from locus_agent.config import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    set_workspace_id(WS_A)

    from locus_agent.mcp_.config import MCPServerConfig

    cfg = MCPServerConfig(name="demo", transport="stdio", command=["echo"])
    await run_in_thread(add_mcp_server, cfg)

    listed = await run_in_thread(list_mcp_servers)
    assert [s.name for s in listed] == ["demo"]

    found = await run_in_thread(get_mcp_server, "demo")
    assert found is not None
    assert found.name == "demo"

    set_workspace_id(WS_B)
    assert await run_in_thread(get_mcp_server, "demo") is None
