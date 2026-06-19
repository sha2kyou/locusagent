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


def has_openai_tool_calls(tool_calls: Any) -> bool:
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    first = tool_calls[0]
    return isinstance(first, dict) and ("function" in first or first.get("type") == "function")


def normalize_assistant_for_llm_api(msg: dict[str, Any]) -> dict[str, Any] | None:
    """OpenAI 兼容 API 要求 assistant 必须有 content 或 tool_calls。

    流式中断时可能只落库 reasoning_content；回放上下文时将其提升为 content。
    若三者皆空则返回 None（调用方应跳过该条）。
    """
    if msg.get("role") != "assistant":
        return msg
    out = dict(msg)
    content = str(out.get("content") or "")
    reasoning = str(out.get("reasoning_content") or "").strip()
    if has_openai_tool_calls(out.get("tool_calls")):
        if not content.strip():
            out.pop("content", None)
        return out
    if content.strip():
        return out
    if reasoning:
        out["content"] = reasoning
        return out
    return None


def normalize_messages_for_llm_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "assistant":
            normalized = normalize_assistant_for_llm_api(msg)
            if normalized is not None:
                out.append(normalized)
            continue
        out.append(msg)
    return out


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
