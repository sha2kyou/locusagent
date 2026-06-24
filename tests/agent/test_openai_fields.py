from locus_agent.core.openai_fields import (
    normalize_assistant_for_llm_api,
    normalize_messages_for_llm_api,
    prepare_assistant_for_llm_context,
    repair_incomplete_tool_rounds,
)


def test_normalize_promotes_reasoning_only_assistant():
    msg = {"role": "assistant", "reasoning_content": "Now save the artifact."}
    out = normalize_assistant_for_llm_api(msg)
    assert out is not None
    assert out["content"] == "Now save the artifact."
    assert out["reasoning_content"] == "Now save the artifact."


def test_normalize_keeps_tool_calls_without_content():
    msg = {
        "role": "assistant",
        "reasoning_content": "thinking",
        "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "fs", "arguments": "{}"}}],
    }
    out = normalize_assistant_for_llm_api(msg)
    assert out is not None
    assert "content" not in out
    assert out["tool_calls"][0]["id"] == "call_1"


def test_normalize_drops_empty_assistant():
    assert normalize_assistant_for_llm_api({"role": "assistant"}) is None


def test_normalize_messages_skips_invalid_assistant():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "reasoning_content": "only reasoning"},
        {"role": "user", "content": "again"},
    ]
    out = normalize_messages_for_llm_api(msgs)
    assert len(out) == 3
    assert out[1]["content"] == "only reasoning"


def test_repair_strips_incomplete_tool_calls_and_orphan_tools():
    msgs = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "checking",
            "tool_calls": [
                {"id": "call_a", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_b", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": "ok"},
        {"role": "user", "content": "follow up"},
    ]
    out = repair_incomplete_tool_rounds(msgs)
    assert out[1]["role"] == "assistant"
    assert out[1]["content"] == "checking"
    assert "tool_calls" not in out[1]
    assert out[2]["role"] == "user"


def test_normalize_messages_repairs_incomplete_tool_round():
    msgs = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "partial",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "fs", "arguments": "{}"}},
            ],
        },
        {"role": "user", "content": "retry"},
    ]
    out = normalize_messages_for_llm_api(msgs)
    assert len(out) == 3
    assert out[1]["content"] == "partial"
    assert "tool_calls" not in out[1]


def test_repair_keeps_complete_tool_round():
    msgs = [
        {"role": "assistant", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "fs", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ]
    out = repair_incomplete_tool_rounds(msgs)
    assert len(out) == 3
    assert out[0]["tool_calls"][0]["id"] == "call_1"


def test_prepare_assistant_for_llm_context_drops_reasoning_track():
    out = prepare_assistant_for_llm_context(
        content="final answer",
        reasoning_content="internal thinking",
    )
    assert out == {"role": "assistant", "content": "final answer"}


def test_prepare_assistant_for_llm_context_promotes_reasoning_only_without_track():
    out = prepare_assistant_for_llm_context(reasoning_content="only reasoning")
    assert out == {"role": "assistant", "content": "only reasoning"}


def test_prepare_assistant_for_llm_context_keeps_tool_calls():
    out = prepare_assistant_for_llm_context(
        reasoning_content="thinking",
        tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "fs", "arguments": "{}"}}],
    )
    assert out is not None
    assert "content" not in out
    assert "reasoning_content" not in out
    assert out["tool_calls"][0]["id"] == "call_1"
