from locus_agent.core.openai_fields import (
    normalize_assistant_for_llm_api,
    normalize_messages_for_llm_api,
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
