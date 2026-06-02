"""System prompt 缓存与工具列表测试。"""

from __future__ import annotations

from agentpod_agent.core.system_prompt import (
    FROZEN_SYSTEM_PROMPT_VERSION,
    _unwrap_system_prompt_cache,
    _wrap_system_prompt_cache,
)
from agentpod_agent.tools.base import Tool, ToolResult
from agentpod_agent.tools.registry import ToolRegistry


def test_cache_invalidates_when_fingerprint_changes():
    prompt = "hello"
    wrapped_a = _wrap_system_prompt_cache(prompt, "aaa")
    wrapped_b = _wrap_system_prompt_cache(prompt, "bbb")
    assert _unwrap_system_prompt_cache(wrapped_a, "aaa") == prompt
    assert _unwrap_system_prompt_cache(wrapped_a, "bbb") is None
    assert _unwrap_system_prompt_cache(wrapped_b, "bbb") == prompt


def test_cache_prefix_includes_version():
    wrapped = _wrap_system_prompt_cache("body", "fp123")
    assert wrapped.startswith(f"agentpod:sp:v{FROZEN_SYSTEM_PROMPT_VERSION}:fp123:")


def test_tool_registry_lists_builtin_tools():
    registry = ToolRegistry()
    names = {t.name for t in registry.list()}
    assert "read_file" in names
    assert "memory" in names
    assert "manage_workspace" in names


async def _noop_handler(_args):
    return ToolResult(content="ok")


def test_tool_registry_thread_safe_register():
    registry = ToolRegistry()
    tool = Tool(name="test_tool_x", description="d", parameters={}, handler=_noop_handler, category="builtin")
    registry.register(tool)
    assert registry.get("test_tool_x") is tool
    registry.unregister("test_tool_x")
    assert registry.get("test_tool_x") is None
