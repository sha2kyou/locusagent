"""System prompt 缓存与工具列表测试。"""

from __future__ import annotations

from agentpod_agent.core.system_prompt import (
    FROZEN_SYSTEM_PROMPT_VERSION,
    _CTX_DELIMITER,
    _unwrap_stable_context_cache,
    _wrap_stable_context_cache,
    assemble_system_prompt,
    build_context_prompt,
)
from agentpod_agent.tools.base import Tool, ToolResult
from agentpod_agent.tools.registry import ToolRegistry


def test_stable_context_cache_invalidates_when_fingerprint_changes():
    stable = "stable-body"
    context = "ctx-body"
    wrapped_a = _wrap_stable_context_cache(stable, context, "aaa")
    wrapped_b = _wrap_stable_context_cache(stable, context, "bbb")
    assert _unwrap_stable_context_cache(wrapped_a, "aaa") == (stable, context)
    assert _unwrap_stable_context_cache(wrapped_a, "bbb") is None
    assert _unwrap_stable_context_cache(wrapped_b, "bbb") == (stable, context)


def test_cache_prefix_includes_version_and_context_delimiter():
    wrapped = _wrap_stable_context_cache("stable", "context", "fp123")
    assert wrapped.startswith(f"agentpod:sp:v{FROZEN_SYSTEM_PROMPT_VERSION}:fp123:")
    assert _CTX_DELIMITER in wrapped


async def test_build_context_prompt_includes_workspace_summary(monkeypatch):
    async def _fake_summary(*, recent_limit: int = 5):
        assert recent_limit == 5
        return "## 技能 (1)\n- demo [private]: test", {"skills": {"count": 1}}

    monkeypatch.setattr(
        "agentpod_agent.workspace_summary.build_workspace_summary",
        _fake_summary,
    )
    monkeypatch.setattr("agentpod_agent.workspace.get_workspace_id", lambda: "ws_test1234")

    text = await build_context_prompt(session_id="sess_1")
    assert "## 工作区上下文（ws_test1234）" in text
    assert "环境变量仅列名称" in text
    assert "## 技能 (1)" in text


def test_assemble_system_prompt_joins_three_tiers():
    full = assemble_system_prompt({"stable": "A", "context": "B", "volatile": "C"})
    assert full == "A\n\nB\n\nC"
    partial = assemble_system_prompt({"stable": "A", "context": "", "volatile": "C"})
    assert partial == "A\n\nC"


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
