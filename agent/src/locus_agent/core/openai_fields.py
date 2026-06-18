"""OpenAI 兼容消息字段：reasoning_content 与 content 分轨。"""

from __future__ import annotations

from typing import Any


def openai_message_text(msg: Any) -> str:
    content = getattr(msg, "content", None) or ""
    return str(content) if content else ""


def openai_message_reasoning(msg: Any) -> str:
    reasoning = getattr(msg, "reasoning_content", None) or ""
    return str(reasoning) if reasoning else ""


def openai_delta_content(delta: Any) -> str:
    content = getattr(delta, "content", None) or ""
    return str(content) if content else ""


def openai_delta_reasoning(delta: Any) -> str:
    reasoning = getattr(delta, "reasoning_content", None) or ""
    return str(reasoning) if reasoning else ""


def openai_completion_text(resp: Any) -> str:
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return ""
    return openai_message_text(choices[0].message)


def assistant_message_dict(
    *,
    content: str = "",
    reasoning_content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant"}
    if content:
        out["content"] = content
    if reasoning_content:
        out["reasoning_content"] = reasoning_content
    if tool_calls:
        out["tool_calls"] = tool_calls
    return out
