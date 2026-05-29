"""上下文压缩：超限时先 LLM 蒸馏中间旧消息为摘要，再保留 system + 摘要 + 最近 N 轮。"""

from __future__ import annotations

from typing import Any

import tiktoken

from ..config import get_settings
from ..logging import get_logger

log = get_logger("context")

# CJK 字符 token 密度远高于 ASCII：分别估算，避免中文被严重低估导致超限
_CJK_TOKENS_PER_CHAR = 0.6
_OTHER_TOKENS_PER_CHAR = 0.25


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x3000 <= o <= 0x303F  # CJK 标点
        or 0x3040 <= o <= 0x30FF  # 日文假名
        or 0x3400 <= o <= 0x4DBF  # CJK 扩展 A
        or 0x4E00 <= o <= 0x9FFF  # CJK 基本汉字
        or 0xF900 <= o <= 0xFAFF  # CJK 兼容
        or 0xFF00 <= o <= 0xFFEF  # 全角字符
    )


def _estimate_text_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    return int(cjk * _CJK_TOKENS_PER_CHAR + other * _OTHER_TOKENS_PER_CHAR)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    try:
        return _estimate_tokens_by_tiktoken(messages, model=get_settings().llm_model)
    except Exception as exc:
        log.warning("token_estimate_fallback", error=str(exc))
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += _estimate_text_tokens(c)
        for tc in m.get("tool_calls") or []:
            total += _estimate_text_tokens(str(tc))
    return total


_ENCODING_CACHE: dict[str, tiktoken.Encoding] = {}


def _encoding_for_model(model: str | None) -> tiktoken.Encoding:
    key = (model or "").strip() or "__default__"
    enc = _ENCODING_CACHE.get(key)
    if enc is not None:
        return enc
    if key == "__default__":
        enc = tiktoken.get_encoding("o200k_base")
    else:
        try:
            enc = tiktoken.encoding_for_model(key)
        except KeyError:
            enc = tiktoken.get_encoding("o200k_base")
    _ENCODING_CACHE[key] = enc
    return enc


def _estimate_tokens_by_tiktoken(messages: list[dict[str, Any]], *, model: str | None) -> int:
    enc = _encoding_for_model(model)
    # 兼容 Chat Completions 的经验开销：每条消息 +3，整体 +3，name 字段 +1。
    total = 3
    for m in messages:
        total += 3
        role = m.get("role")
        if isinstance(role, str):
            total += len(enc.encode(role))
        name = m.get("name")
        if isinstance(name, str) and name:
            total += len(enc.encode(name)) + 1
        c = m.get("content")
        if isinstance(c, str):
            total += len(enc.encode(c))
        for tc in m.get("tool_calls") or []:
            total += len(enc.encode(str(tc)))
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


_DISTILL_SYSTEM_PROMPT = (
    "你是对话压缩器。把下面这段较早的对话/工具调用浓缩成要点摘要，"
    "保留：用户目标、已确定的结论与决策、关键事实/数据、未完成事项。"
    "丢弃寒暄与冗余。简体中文，分条，尽量精简。"
)


def _drop_leading_tool(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """确保序列不以 tool 消息开头（否则缺少配对的 assistant tool_calls 会报错）。"""
    out = list(msgs)
    while out and out[0].get("role") == "tool":
        out.pop(0)
    return out


async def _distill_messages(messages: list[dict[str, Any]], *, client, model: str) -> str:
    convo: list[str] = []
    for m in messages:
        role = str(m.get("role") or "")
        if role == "system":
            continue
        content = str(m.get("content") or "").strip()
        tool_calls = m.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            names = [
                str((tc.get("function") or {}).get("name") or "")
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
            names = [n for n in names if n]
            if names:
                convo.append(f"[assistant 调用工具] {', '.join(names)}")
        if content:
            convo.append(f"[{role}] {content[:800]}")
    text = "\n".join(convo)[:8000]
    if not text.strip():
        return ""
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _DISTILL_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        max_tokens=500,
        temperature=0.2,
    )
    return ((resp.choices or [None])[0].message.content if resp.choices else "") or ""


async def compress(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    client,
    model: str,
    keep_last: int = 8,
    min_middle: int = 4,
) -> list[dict[str, Any]]:
    compressed, _ = await compress_with_report(
        messages,
        max_tokens=max_tokens,
        client=client,
        model=model,
        keep_last=keep_last,
        min_middle=min_middle,
    )
    return compressed


async def compress_with_report(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    client,
    model: str,
    keep_last: int = 8,
    min_middle: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """超限时蒸馏中间旧消息为摘要；蒸馏失败则退化为硬截断。"""
    before_tokens = estimate_tokens(messages)
    if before_tokens <= max_tokens:
        return messages, {
            "triggered": False,
            "mode": "none",
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "summary": "",
        }

    head: list[dict[str, Any]] = []
    body = list(messages)
    if body and body[0].get("role") == "system":
        head = [body[0]]
        body = body[1:]
    if len(body) <= keep_last:
        out = head + body
        after_tokens = estimate_tokens(out)
        return out, {
            "triggered": True,
            "mode": "truncate",
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "summary": "",
        }

    tail = body[-keep_last:]
    middle = body[:-keep_last]
    # tail 不能以 tool 开头：把开头的孤立 tool 消息并入 middle（一起被摘要）
    while tail and tail[0].get("role") == "tool":
        middle.append(tail.pop(0))
    if not tail:
        out = truncate(messages, max_tokens=max_tokens, keep_last=keep_last)
        after_tokens = estimate_tokens(out)
        return out, {
            "triggered": True,
            "mode": "truncate",
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "summary": "",
        }

    summary_text = ""
    summary_msgs: list[dict[str, Any]] = []
    if len(middle) >= min_middle:
        try:
            summary = await _distill_messages(middle, client=client, model=model)
            if summary.strip():
                summary_text = summary.strip()
                summary_msgs = [
                    {
                        "role": "system",
                        "content": "## 历史对话摘要（更早的消息已压缩）\n" + summary_text,
                    }
                ]
        except Exception as exc:
            log.warning("context_distill_failed", error=str(exc))

    while len(tail) > 1 and estimate_tokens(head + summary_msgs + tail) > max_tokens:
        tail = _drop_leading_tool(tail[1:])
        if not tail:
            break
    out = head + summary_msgs + tail
    after_tokens = estimate_tokens(out)
    mode = "distill" if summary_text else "truncate"
    return out, {
        "triggered": True,
        "mode": mode,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "summary": summary_text,
    }
