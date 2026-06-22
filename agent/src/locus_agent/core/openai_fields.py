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


def _assistant_tool_call_ids(msg: dict[str, Any]) -> set[str]:
    tool_calls = msg.get("tool_calls")
    if not has_openai_tool_calls(tool_calls):
        return set()
    ids: set[str] = set()
    for tc in tool_calls:
        if isinstance(tc, dict):
            tc_id = str(tc.get("id") or "").strip()
            if tc_id:
                ids.add(tc_id)
    return ids


def repair_incomplete_tool_rounds(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉 assistant 上未收齐 tool 回复的 tool_calls, 并丢弃紧随其后的残缺 tool 消息。"""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        expected_ids = _assistant_tool_call_ids(msg) if msg.get("role") == "assistant" else set()
        if not expected_ids:
            out.append(msg)
            i += 1
            continue

        j = i + 1
        tool_msgs: list[dict[str, Any]] = []
        found_ids: set[str] = set()
        while j < len(messages) and messages[j].get("role") == "tool":
            tmsg = messages[j]
            tool_msgs.append(tmsg)
            tc_id = str(tmsg.get("tool_call_id") or "").strip()
            if tc_id:
                found_ids.add(tc_id)
            j += 1

        if expected_ids <= found_ids:
            out.append(msg)
            out.extend(tool_msgs)
        else:
            repaired = dict(msg)
            repaired.pop("tool_calls", None)
            normalized = normalize_assistant_for_llm_api(repaired)
            if normalized is not None:
                out.append(normalized)
        i = j
    return out


def normalize_messages_for_llm_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in repair_incomplete_tool_rounds(messages):
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
