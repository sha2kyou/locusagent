"""工具轮次上限收尾逻辑测试。"""

from __future__ import annotations

from agentpod_agent.core.loop import (
    _ensure_user_visible_text,
    _finalize_request_kwargs,
    _TOOL_ROUND_LIMIT_FALLBACK,
    _TOOL_ROUND_LIMIT_NOTICE,
)


def test_ensure_user_visible_text_uses_fallback_when_empty():
    assert _ensure_user_visible_text("", fallback="fallback") == "fallback"
    assert _ensure_user_visible_text("  ", fallback="fallback") == "fallback"
    assert _ensure_user_visible_text("ok", fallback="fallback") == "ok"


def test_finalize_request_kwargs_disables_tools():
    kwargs = _finalize_request_kwargs(
        model="gpt-test",
        working_messages=[{"role": "user", "content": "hi"}],
        extra={"tools": [{"type": "function"}], "tool_choice": "auto", "temperature": 0.2},
        notice=_TOOL_ROUND_LIMIT_NOTICE,
    )
    assert kwargs["tool_choice"] == "none"
    assert "tools" not in kwargs
    assert kwargs["temperature"] == 0.2
    assert kwargs["messages"][-1]["content"] == _TOOL_ROUND_LIMIT_NOTICE


def test_tool_round_limit_fallback_is_user_visible_english():
    assert "Tool-call limit" in _TOOL_ROUND_LIMIT_FALLBACK
