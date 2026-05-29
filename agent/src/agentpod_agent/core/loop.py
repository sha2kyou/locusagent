"""对话循环：tool call → dispatch → 结果回灌 → 继续。

P0 非流式：完整等待 LLM 回复后再返回；后续可加流式。
约束：
- 最大轮次 max_loop_rounds，超出抛错
- Tool 异常包装为 tool message 回灌（不直接 5xx）
- 上下文压缩：估算 token > 模型上限 × ratio 时截断
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any

from openai.types.chat import ChatCompletion

from ..config import get_settings
from ..logging import get_logger
from ..tools import ToolError, ToolRegistry
from .context import compress, compress_with_report
from .llm import get_llm_client

log = get_logger("loop")

MODEL_TOKEN_LIMITS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-4.1-mini": 1_000_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_000,
}
DEFAULT_TOKEN_LIMIT = 32_000
_TOOL_ROUND_LIMIT_NOTICE = (
    "工具调用轮次已达到上限。请立即停止继续调用任何工具（包括 tool/mcp/skill/memory），"
    "基于当前已知信息给出最终结论，并明确说明剩余不确定项。"
)


def _model_limit(model: str) -> int:
    return MODEL_TOKEN_LIMITS.get(model, DEFAULT_TOKEN_LIMIT)


@dataclass(slots=True)
class LoopResult:
    final_text: str
    rounds: int
    total_tokens: int
    tool_calls_made: int


def _serialize_message(msg) -> dict[str, Any]:
    out: dict[str, Any] = {"role": msg.role}
    if msg.content is not None:
        out["content"] = msg.content
    if getattr(msg, "tool_calls", None):
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return out


def _normalize_chat_tool_calls(
    tool_calls: Iterable[Any],
    *,
    id_prefix: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, tc in enumerate(tool_calls):
        fn = getattr(tc, "function", None)
        tc_id = str(getattr(tc, "id", "") or "").strip() or f"{id_prefix}-{idx}"
        name = str(getattr(fn, "name", "") or "")
        arguments = str(getattr(fn, "arguments", "") or "")
        normalized.append(
            {
                "id": tc_id,
                "type": str(getattr(tc, "type", "function") or "function"),
                "function": {"name": name, "arguments": arguments},
            }
        )
    return normalized


def _cap_clarify_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每轮最多保留一个 clarify 调用：一次只向用户抛出一个待选问题。

    在拼装 assistant 消息与执行之前裁剪，被丢弃的调用不会进入 working，
    因此不会出现没有对应 tool 结果的悬空 tool_call。
    """
    out: list[dict[str, Any]] = []
    has_clarify = False
    for c in calls:
        if (c.get("function") or {}).get("name") == "clarify":
            if has_clarify:
                continue
            has_clarify = True
        out.append(c)
    return out


async def _execute_one_tool_call(registry: ToolRegistry, tc: Any) -> dict[str, Any]:
    name = tc.function.name
    raw_args = tc.function.arguments or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except json.JSONDecodeError as exc:
        log.warning("tool_args_parse_failed", tool=name, error=str(exc))
        return {
            "role": "tool",
            "tool_call_id": tc.id,
            "content": f"Error: invalid JSON arguments: {exc}",
        }
    try:
        result = await registry.call(name, args)
        log.info("tool_executed", tool=name)
        return {"role": "tool", "tool_call_id": tc.id, "content": result.to_message()}
    except ToolError as exc:
        log.warning("tool_failed", tool=name, error=str(exc))
        return {"role": "tool", "tool_call_id": tc.id, "content": f"Error: {exc}"}


async def _execute_tool_calls(
    registry: ToolRegistry,
    tool_calls: Iterable[Any],
) -> list[dict[str, Any]]:
    """并行执行同一轮的多个工具调用（gather 保持原顺序）。"""
    calls = list(tool_calls)
    if not calls:
        return []
    if len(calls) == 1:
        return [await _execute_one_tool_call(registry, calls[0])]
    return list(await asyncio.gather(*(_execute_one_tool_call(registry, tc) for tc in calls)))


async def _finalize_without_tools(
    *,
    client,
    model: str,
    working_messages: list[dict[str, Any]],
    extra: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, int]:
    req_messages = list(working_messages)
    req_messages.append({"role": "system", "content": _TOOL_ROUND_LIMIT_NOTICE})
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": req_messages,
    }
    if extra:
        kwargs.update(extra)
    completion: ChatCompletion = await client.chat.completions.create(**kwargs)
    usage_tokens = int((completion.usage.total_tokens if completion.usage else 0) or 0)
    msg = completion.choices[0].message
    msg_dict = _serialize_message(msg)
    return msg_dict, str(msg.content or ""), usage_tokens


async def run_chat_loop(
    messages: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[LoopResult, list[dict[str, Any]]]:
    settings = get_settings()
    chosen_model = model or settings.llm_model
    max_rounds = settings.max_loop_rounds
    token_limit = int(_model_limit(chosen_model) * settings.context_compress_ratio)
    client = get_llm_client()
    tools_schema = registry.schemas() or None
    max_tool_rounds = max(1, settings.max_tool_rounds)

    working = list(messages)
    total_tokens = 0
    tool_calls_made = 0
    tool_rounds_made = 0
    final_text = ""

    for round_idx in range(1, max_rounds + 1):
        working = await compress(
            working,
            max_tokens=token_limit,
            client=client,
            model=chosen_model,
            keep_last=settings.context_keep_last,
            min_middle=settings.context_distill_min_middle,
        )
        log.info(
            "loop_round_start",
            round=round_idx,
            messages=len(working),
            tools=len(tools_schema or []),
        )
        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "messages": working,
        }
        if tools_schema:
            kwargs["tools"] = tools_schema
            kwargs["tool_choice"] = "auto"
        if extra:
            kwargs.update(extra)

        completion: ChatCompletion = await client.chat.completions.create(**kwargs)
        usage = completion.usage
        if usage:
            total_tokens += usage.total_tokens or 0

        choice = completion.choices[0]
        msg = choice.message

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            normalized_calls = _normalize_chat_tool_calls(
                msg.tool_calls,
                id_prefix=f"call-r{round_idx}",
            )
            normalized_calls = _cap_clarify_calls(normalized_calls)
            assistant_msg: dict[str, Any] = {"role": "assistant", "tool_calls": normalized_calls}
            if msg.content is not None:
                assistant_msg["content"] = msg.content
            working.append(assistant_msg)
            if tool_rounds_made >= max_tool_rounds:
                log.warning(
                    "loop_tool_round_limit_reached",
                    round=round_idx,
                    tool_rounds=tool_rounds_made,
                    max_tool_rounds=max_tool_rounds,
                )
                final_msg, final_text, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=chosen_model,
                    working_messages=working,
                    extra=extra,
                )
                total_tokens += more_tokens
                working.append(final_msg)
                return (
                    LoopResult(
                        final_text=final_text or "[tool round limit reached]",
                        rounds=round_idx,
                        total_tokens=total_tokens,
                        tool_calls_made=tool_calls_made,
                    ),
                    working,
                )
            tool_rounds_made += 1
            tool_calls_made += len(normalized_calls)
            stub_calls = [_ToolCallStub(raw) for raw in normalized_calls]
            tool_results = await _execute_tool_calls(registry, stub_calls)
            working.extend(tool_results)
            # clarify 是终结性工具：执行后立即返回，不再续跑下一轮
            if any(s.function.name == "clarify" for s in stub_calls):
                return (
                    LoopResult(
                        final_text=msg.content or "",
                        rounds=round_idx,
                        total_tokens=total_tokens,
                        tool_calls_made=tool_calls_made,
                    ),
                    working,
                )
            continue

        working.append(_serialize_message(msg))
        final_text = msg.content or ""
        log.info("loop_finished", round=round_idx, tokens=total_tokens)
        return (
            LoopResult(
                final_text=final_text,
                rounds=round_idx,
                total_tokens=total_tokens,
                tool_calls_made=tool_calls_made,
            ),
            working,
        )

    log.warning("loop_max_rounds_exceeded", rounds=max_rounds)
    return (
        LoopResult(
            final_text=final_text or "[max rounds reached]",
            rounds=max_rounds,
            total_tokens=total_tokens,
            tool_calls_made=tool_calls_made,
        ),
        working,
    )


class _ToolCallStub:
    """重组流式 tool_call delta 后用于复用 _execute_tool_calls 的最小对象。"""

    __slots__ = ("id", "type", "function")

    def __init__(self, raw: dict[str, Any]) -> None:
        self.id = raw["id"]
        self.type = raw.get("type", "function")
        fn = raw.get("function") or {}

        class _F:
            __slots__ = ("name", "arguments")

            def __init__(self, name: str, arguments: str) -> None:
                self.name = name
                self.arguments = arguments

        self.function = _F(fn.get("name", ""), fn.get("arguments", ""))


async def run_chat_loop_stream(
    messages: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式 chat loop。

    yield 事件类型：
    - {"type": "delta", "content": str}                       LLM 增量输出
    - {"type": "tool_call", "name": str, "id": str}           工具开始
    - {"type": "tool_result", "tool_call_id": str, "preview": str}
    - {"type": "done", "final_text", "rounds", "total_tokens", "tool_calls_made"}
    """
    settings = get_settings()
    chosen_model = model or settings.llm_model
    max_rounds = settings.max_loop_rounds
    token_limit = int(_model_limit(chosen_model) * settings.context_compress_ratio)
    client = get_llm_client()
    tools_schema = registry.schemas() or None
    max_tool_rounds = max(1, settings.max_tool_rounds)

    working = list(messages)
    total_tokens = 0
    tool_calls_made = 0
    tool_rounds_made = 0
    final_text = ""

    for round_idx in range(1, max_rounds + 1):
        working, compression_report = await compress_with_report(
            working,
            max_tokens=token_limit,
            client=client,
            model=chosen_model,
            keep_last=settings.context_keep_last,
            min_middle=settings.context_distill_min_middle,
        )
        if compression_report.get("triggered"):
            call_id = f"auto-summarize-r{round_idx}"
            mode = str(compression_report.get("mode") or "truncate")
            before_tokens = int(compression_report.get("before_tokens") or 0)
            after_tokens = int(compression_report.get("after_tokens") or 0)
            summary_text = str(compression_report.get("summary") or "").strip()
            tool_args = json.dumps(
                {
                    "text": f"[auto-context-compress mode={mode} before={before_tokens} after={after_tokens}]",
                    "max_tokens": 500,
                },
                ensure_ascii=False,
            )
            yield {
                "type": "assistant_tools",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": "summarize", "arguments": tool_args},
                        }
                    ],
                    "content": "已自动执行上下文压缩。",
                },
            }
            yield {"type": "tool_call", "name": "summarize", "id": call_id}
            if summary_text:
                tool_content = (
                    f"【自动上下文压缩】mode={mode}, tokens: {before_tokens} -> {after_tokens}\n\n"
                    f"{summary_text}"
                )
            else:
                tool_content = (
                    f"【自动上下文压缩】mode={mode}, tokens: {before_tokens} -> {after_tokens}\n"
                    "本次未生成可展示摘要（已进行截断保留）。"
                )
            yield {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": "summarize",
                "preview": tool_content[:1000],
                "content": tool_content,
            }
        log.info(
            "loop_round_start",
            round=round_idx,
            messages=len(working),
            tools=len(tools_schema or []),
            stream=True,
        )
        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "messages": working,
            "stream": True,
        }
        if tools_schema:
            kwargs["tools"] = tools_schema
            kwargs["tool_choice"] = "auto"
        if extra:
            kwargs.update(extra)

        stream = await client.chat.completions.create(**kwargs)

        accum_content = ""
        accum_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None

        async for event in stream:
            if event.usage:
                total_tokens += event.usage.total_tokens or 0
            if not event.choices:
                continue
            choice = event.choices[0]
            delta = choice.delta
            if delta is not None:
                if delta.content:
                    accum_content += delta.content
                    yield {"type": "delta", "content": delta.content}
                tcs = getattr(delta, "tool_calls", None)
                if tcs:
                    for tc_delta in tcs:
                        idx = tc_delta.index
                        bucket = accum_tool_calls.setdefault(
                            idx,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if tc_delta.id:
                            bucket["id"] = tc_delta.id
                        if tc_delta.type:
                            bucket["type"] = tc_delta.type
                        if tc_delta.function:
                            if tc_delta.function.name:
                                bucket["function"]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                bucket["function"]["arguments"] += tc_delta.function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        normalized_tool_calls: list[dict[str, Any]] = []
        if accum_tool_calls:
            sorted_idx = sorted(accum_tool_calls)
            for pos, idx in enumerate(sorted_idx):
                raw = dict(accum_tool_calls[idx])
                if not str(raw.get("id") or "").strip():
                    raw["id"] = f"call-r{round_idx}-{pos}"
                normalized_tool_calls.append(raw)
        normalized_tool_calls = _cap_clarify_calls(normalized_tool_calls)

        msg_dict: dict[str, Any] = {"role": "assistant"}
        if accum_content:
            msg_dict["content"] = accum_content
        if normalized_tool_calls:
            msg_dict["tool_calls"] = normalized_tool_calls
        working.append(msg_dict)

        if finish_reason == "tool_calls" and normalized_tool_calls:
            if tool_rounds_made >= max_tool_rounds:
                log.warning(
                    "loop_tool_round_limit_reached",
                    round=round_idx,
                    tool_rounds=tool_rounds_made,
                    max_tool_rounds=max_tool_rounds,
                    stream=True,
                )
                final_msg, capped_text, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=chosen_model,
                    working_messages=working,
                    extra=extra,
                )
                total_tokens += more_tokens
                working.append(final_msg)
                if capped_text:
                    yield {"type": "delta", "content": capped_text}
                final_text = capped_text
                yield {
                    "type": "done",
                    "final_text": final_text or "[tool round limit reached]",
                    "rounds": round_idx,
                    "total_tokens": total_tokens,
                    "tool_calls_made": tool_calls_made,
                }
                return
            tool_rounds_made += 1
            tool_calls_made += len(normalized_tool_calls)
            stub_calls = [_ToolCallStub(raw) for raw in normalized_tool_calls]
            yield {"type": "assistant_tools", "message": msg_dict}
            for stub in stub_calls:
                yield {"type": "tool_call", "name": stub.function.name, "id": stub.id}
            tool_results = await _execute_tool_calls(registry, stub_calls)
            for stub, r in zip(stub_calls, tool_results):
                preview = (r.get("content") or "")[:1000]
                yield {
                    "type": "tool_result",
                    "tool_call_id": r["tool_call_id"],
                    "name": stub.function.name,
                    "preview": preview,
                    "content": r.get("content") or "",
                }
            working.extend(tool_results)
            # clarify 是终结性工具：抛出选项卡片后立即收尾，不再续跑下一轮，等待用户选择
            if any(s.function.name == "clarify" for s in stub_calls):
                yield {
                    "type": "done",
                    "final_text": accum_content,
                    "rounds": round_idx,
                    "total_tokens": total_tokens,
                    "tool_calls_made": tool_calls_made,
                }
                return
            continue

        final_text = accum_content
        log.info("loop_finished", round=round_idx, tokens=total_tokens, stream=True)
        yield {
            "type": "done",
            "final_text": final_text,
            "rounds": round_idx,
            "total_tokens": total_tokens,
            "tool_calls_made": tool_calls_made,
        }
        return

    log.warning("loop_max_rounds_exceeded", rounds=max_rounds, stream=True)
    yield {
        "type": "done",
        "final_text": final_text or "[max rounds reached]",
        "rounds": max_rounds,
        "total_tokens": total_tokens,
        "tool_calls_made": tool_calls_made,
    }
