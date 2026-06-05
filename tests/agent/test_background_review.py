"""background review 摘要提取单元测试。"""

from __future__ import annotations

from agentpod_agent.core.background_review import summarize_background_review_actions


def test_summarize_uses_tool_name_not_keywords() -> None:
    prior: list[dict] = []
    review = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call-1", "function": {"name": "memory", "arguments": "{}"}},
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": "已写入 memory#12",
        },
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call-2", "function": {"name": "read_file", "arguments": "{}"}},
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-2",
            "content": "created helper output",
        },
    ]
    actions = summarize_background_review_actions(review, prior)
    assert actions == ["已写入 memory#12"]


def test_summarize_skips_errors_and_noop() -> None:
    review = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call-1", "function": {"name": "skill_manage", "arguments": "{}"}},
                {"id": "call-2", "function": {"name": "memory", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "Error: denied"},
        {"role": "tool", "tool_call_id": "call-2", "content": "Nothing to save."},
    ]
    assert summarize_background_review_actions(review, []) == []
