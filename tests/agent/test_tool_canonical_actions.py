"""内置工具 canonical action / 参数字段测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.tools.attachments import _attachments_tool
from agentpod_agent.tools.base import ToolError
from agentpod_agent.tools.env_vars import _env_vars_tool
from agentpod_agent.tools.mcp_manage import _mcp_manage
from agentpod_agent.tools.memory import _memory_tool
from agentpod_agent.tools.scheduled_tasks import _scheduled_task_manage
from agentpod_agent.tools.skills import _skill_manage


@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("replace", {"content": "x"}),
        ("remove", {}),
    ],
)
async def test_memory_replace_remove_require_id(action: str, extra: dict) -> None:
    with pytest.raises(ToolError, match="id is required"):
        await _memory_tool({"action": action, "term": "short_term", **extra})


@pytest.mark.parametrize("action", ["update", "delete"])
async def test_memory_rejects_legacy_actions(action: str) -> None:
    with pytest.raises(ToolError, match="unknown action"):
        await _memory_tool({"action": action, "id": 1, "content": "x", "term": "short_term"})


async def test_env_vars_rejects_remove_alias() -> None:
    with pytest.raises(ToolError, match="unknown action"):
        await _env_vars_tool({"action": "remove", "name": "FOO"})


async def test_scheduled_task_manage_rejects_edit_remove() -> None:
    for action in ("edit", "remove"):
        with pytest.raises(ToolError, match="unknown action"):
            await _scheduled_task_manage({"action": action, "id": 1})


async def test_mcp_manage_rejects_edit_delete() -> None:
    for action in ("edit", "delete"):
        with pytest.raises(ToolError, match="unknown action"):
            await _mcp_manage({"action": action, "name": "srv"})


async def test_skill_manage_rejects_edit() -> None:
    with pytest.raises(ToolError, match="unknown action"):
        await _skill_manage({"action": "edit", "name": "demo"})


@pytest.mark.parametrize("action", ["query", "fetch", "attach"])
async def test_attachments_rejects_legacy_actions(action: str) -> None:
    with pytest.raises(ToolError, match="unknown action"):
        await _attachments_tool({"action": action, "id": "att_x"})
