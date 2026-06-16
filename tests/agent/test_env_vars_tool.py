"""env_vars 工具脱敏与保留名测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.db import init_db
from agentpod_agent.env_vars import add_env_var
from agentpod_agent.tools.base import ToolError
from agentpod_agent.tools.env_vars import _env_vars_tool
from agentpod_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()


@pytest.mark.asyncio
async def test_env_vars_list_hides_values() -> None:
    await add_env_var("SMTP_PASSWORD", "s3cret", "mail creds")
    result = await _env_vars_tool({"action": "list"})
    assert "s3cret" not in result.content
    assert "SMTP_PASSWORD" in result.content
    assert "(value set)" in result.content
    assert "value" not in (result.metadata.get("items") or [{}])[0]


@pytest.mark.asyncio
async def test_env_vars_add_rejects_reserved_name() -> None:
    with pytest.raises(ToolError, match="reserved env var name"):
        await _env_vars_tool({"action": "add", "name": "PATH", "value": "/evil"})
