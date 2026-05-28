"""上下文压缩：默认截断旧消息，保留 system + 最近 N 轮。

P0 简化：基于消息数估算（token=4 字符），不依赖 tiktoken；后续可替换。
"""

from __future__ import annotations

from typing import Any

ROUGH_TOKENS_PER_CHAR = 0.25


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += int(len(c) * ROUGH_TOKENS_PER_CHAR)
        for tc in m.get("tool_calls") or []:
            total += int(len(str(tc)) * ROUGH_TOKENS_PER_CHAR)
    return total


def truncate(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    keep_system: bool = True,
    keep_last: int = 8,
) -> list[dict[str, Any]]:
    """超过 max_tokens 时截断中间消息，保留 system + 最近 keep_last 条。"""
    if estimate_tokens(messages) <= max_tokens:
        return messages

    head: list[dict[str, Any]] = []
    body = list(messages)
    if keep_system and body and body[0].get("role") == "system":
        head = [body[0]]
        body = body[1:]

    tail = body[-keep_last:]
    truncated = head + tail
    if estimate_tokens(truncated) <= max_tokens:
        return truncated

    while len(tail) > 1 and estimate_tokens(head + tail) > max_tokens:
        tail = tail[1:]
    return head + tail
