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
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any

from openai.types.chat import ChatCompletion

from ..config import get_settings
from ..logging import get_logger
from ..tools import ToolError, ToolRegistry
from ..workspace import get_workspace_id
from .context import compress_with_report
from .models import messages_include_images, resolve_model
from .llm import get_llm_client
from .stream_health import StreamHealthError, iter_with_stream_health
from .run_context import get_chat_session_id, set_chat_session_id
from .session_review_state import reset_memory_nudge, reset_skill_nudge
from .tool_guardrails import (
    ToolCallGuardrailController,
    append_guardrail_guidance,
    guardrail_block_content,
    guardrail_config_from_settings,
    classify_tool_failure,
)
from .openai_fields import (
    assistant_message_dict,
    openai_delta_content,
    openai_delta_reasoning,
    openai_message_reasoning,
    openai_message_text,
)
from .persistence import persist_context_compression
from ..usage_report import schedule_openai_usage

log = get_logger("loop")

MODEL_TOKEN_LIMITS: dict[str, int] = {
    # Anthropic Claude
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4.8": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4.7": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-opus-4.6": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4.6": 1_000_000,
    "claude": 200_000,
    # OpenAI
    "gpt-5.5": 1_050_000,
    "gpt-5.4-nano": 400_000,
    "gpt-5.4-mini": 400_000,
    "gpt-5.4": 1_050_000,
    "gpt-5.3-codex-spark": 128_000,
    "gpt-5.1-chat": 128_000,
    "gpt-5": 400_000,
    "gpt-4.1": 1_047_576,
    "gpt-4o-mini": 128_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 128_000,
    "gpt-3.5-turbo": 16_000,
    # Google
    "gemini": 1_048_576,
    "gemma-4-31b": 256_000,
    "gemma-4": 256_000,
    "gemma4": 256_000,
    "gemma-3": 131_072,
    "gemma": 8_192,
    # DeepSeek
    "deepseek-v4-pro": 1_000_000,
    "deepseek-v4-flash": 1_000_000,
    "deepseek-chat": 1_000_000,
    "deepseek-reasoner": 1_000_000,
    "deepseek": 128_000,
    # Qwen
    "qwen3.6-plus": 1_048_576,
    "qwen3-coder-plus": 1_000_000,
    "qwen3-coder": 262_144,
    "qwen": 131_072,
    # MiniMax / GLM / Kimi / Xiaomi MiMo
    "minimax": 204_800,
    "glm": 202_752,
    "kimi": 262_144,
    "xiaomimimo/mimo-v2-pro": 1_048_576,
    "xiaomimimo/mimo-v2.5-pro": 1_048_576,
    "xiaomimimo/mimo-v2.5": 1_048_576,
    "xiaomimimo/mimo-v2-omni": 262_144,
    "xiaomimimo/mimo-v2-flash": 262_144,
    "mimo-v2-pro": 1_048_576,
    "mimo-v2.5-pro": 1_048_576,
    "mimo-v2.5": 1_048_576,
    "mimo-v2-omni": 262_144,
    "mimo-v2-flash": 262_144,
    # xAI Grok
    "grok-build": 256_000,
    "grok-code-fast": 256_000,
    "grok-2-vision": 8_192,
    "grok-4-fast": 2_000_000,
    "grok-4.20": 2_000_000,
    "grok-4.3": 1_000_000,
    "grok-4": 256_000,
    "grok-3": 131_072,
    "grok-2": 131_072,
    "grok": 131_072,
    # Other common families
    "llama": 131_072,
    "hy3-preview": 262_144,
    "nemotron": 131_072,
    "trinity": 262_144,
    "elephant": 262_144,
    "zai-org/glm-5": 202_752,
}
_MODEL_TOKEN_LIMITS_SORTED: tuple[tuple[str, int], ...] = tuple(
    sorted(MODEL_TOKEN_LIMITS.items(), key=lambda x: len(x[0]), reverse=True)
)
DEFAULT_TOKEN_LIMIT = 256_000
_TOOL_ROUND_LIMIT_NOTICE = (
    "【强制收尾】工具调用轮次已达上限。禁止再调用任何工具（含 tool/mcp/skill/memory）。"
    "你必须立即输出面向用户的中文正文总结：已完成的工作、当前能给出的结论、"
    "因轮次限制未能完成的部分，以及用户可采取的下一步。"
    "禁止返回空回复，禁止仅输出占位符。"
)
_TOOL_ROUND_LIMIT_FALLBACK = (
    "工具调用次数已达上限，无法继续执行更多步骤。"
    "请根据上文工具结果与对话内容自行归纳；若信息不足，请缩小任务范围或说明优先完成哪一部分后重试。"
)
_ARTIFACT_SAVE_LOOP_NOTICE = (
    "你刚完成过一次 artifact_save。请停止继续调用 artifact_save，"
    "直接给用户简短确认结果即可，无需输出链接。"
)
_TOOL_GUARDRAIL_HALT_NOTICE = (
    "【强制收尾】工具循环护栏已触发：同一工具路径重复失败或无进展。"
    "禁止再调用工具。你必须输出面向用户的中文正文总结：已知结论、阻塞原因、"
    "已尝试过的路径，以及建议的下一步。禁止返回空回复。"
)


def _model_limit(model: str) -> int:
    normalized = model.strip().lower()
    if not normalized:
        return DEFAULT_TOKEN_LIMIT
    for name, limit in _MODEL_TOKEN_LIMITS_SORTED:
        if name in normalized:
            return limit
    return DEFAULT_TOKEN_LIMIT


@dataclass(slots=True)
class LoopResult:
    final_text: str
    rounds: int
    total_tokens: int
    tool_calls_made: int
    final_reasoning: str = ""


def _serialize_message(msg) -> dict[str, Any]:
    tool_calls = None
    if getattr(msg, "tool_calls", None):
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return assistant_message_dict(
        content=openai_message_text(msg),
        reasoning_content=openai_message_reasoning(msg),
        tool_calls=tool_calls,
    )


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
    """每轮限制 clarify / artifact_save 重复调用。

    - clarify：每轮最多 1 次（一次只抛一个问题）
    - artifact_save：每轮最多 1 次（避免同轮批量保存副本）

    在拼装 assistant 消息与执行之前裁剪，被丢弃的调用不会进入 working，
    因此不会出现没有对应 tool 结果的悬空 tool_call。
    """
    out: list[dict[str, Any]] = []
    has_clarify = False
    has_artifact_save = False
    for c in calls:
        fn_name = (c.get("function") or {}).get("name")
        if fn_name == "clarify":
            if has_clarify:
                continue
            has_clarify = True
        elif fn_name == "artifact_save":
            if has_artifact_save:
                continue
            has_artifact_save = True
        out.append(c)
    return out


def _all_calls_are(calls: Iterable[Any], tool_name: str) -> bool:
    seq = list(calls)
    return bool(seq) and all(getattr(c.function, "name", "") == tool_name for c in seq)


def _clarify_succeeded(stub_calls: Iterable[Any], tool_results: list[dict[str, Any]]) -> bool:
    from ..tools.clarify import is_clarify_result

    by_id = {r.get("tool_call_id"): r.get("content") or "" for r in tool_results}
    for stub in stub_calls:
        if getattr(stub.function, "name", "") != "clarify":
            continue
        if is_clarify_result(by_id.get(stub.id, "")):
            return True
    return False


def _normalize_disabled_tools(disabled_tools: set[str] | None) -> set[str]:
    return {str(n).strip().lower() for n in (disabled_tools or set()) if str(n).strip()}


def _normalize_blocked_actions(
    blocked_tool_actions: dict[str, set[str]] | None,
) -> dict[str, set[str]]:
    return {
        str(tool).strip().lower(): {
            str(action).strip().lower() for action in actions if str(action).strip()
        }
        for tool, actions in (blocked_tool_actions or {}).items()
        if str(tool).strip()
    }


def _guardrail_skip_result(
    guardrail: ToolCallGuardrailController,
    tc: Any,
) -> dict[str, Any] | None:
    stop = guardrail.turn_stop_decision
    if stop is None or not stop.should_stop_turn:
        return None
    return {
        "role": "tool",
        "tool_call_id": tc.id,
        "content": guardrail_block_content(stop),
    }


def _chat_attachment_from_metadata(metadata: dict[str, Any]) -> dict[str, str] | None:
    raw = metadata.get("chat_attachment")
    if isinstance(raw, dict) and raw.get("id"):
        return {"id": str(raw["id"]), "name": str(raw.get("name") or "file")}
    return None


def _tool_message_for_llm(msg: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in msg.items() if not str(k).startswith("_")}


def _with_elapsed_ms(out: dict[str, Any], started: float) -> dict[str, Any]:
    out["_elapsed_ms"] = max(0, int((time.monotonic() - started) * 1000))
    return out


async def _execute_one_tool_call(
    registry: ToolRegistry,
    tc: Any,
    *,
    blocked_actions: set[str] | None = None,
    guardrail: ToolCallGuardrailController | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    name = tc.function.name
    if guardrail is not None:
        skipped = _guardrail_skip_result(guardrail, tc)
        if skipped is not None:
            return _with_elapsed_ms(skipped, started)
    raw_args = tc.function.arguments or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except json.JSONDecodeError as exc:
        log.warning("tool_args_parse_failed", tool=name, error=str(exc))
        content = f"Error: invalid JSON arguments: {exc}"
        if guardrail is not None:
            post = guardrail.after_call(name, {}, content, failed=True)
            content = append_guardrail_guidance(content, post)
        return _with_elapsed_ms(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            },
            started,
        )
    if guardrail is not None:
        pre = guardrail.before_call(name, args)
        if not pre.allows_execution:
            log.warning(
                "tool_guardrail_block",
                tool=name,
                code=pre.code,
                count=pre.count,
            )
            return _with_elapsed_ms(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": guardrail_block_content(pre),
                },
                started,
            )
    action = str(args.get("action", "")).strip().lower()
    if blocked_actions and action in blocked_actions:
        content = f"Error: action '{action}' is disabled for tool '{name}' in this run"
        if guardrail is not None:
            post = guardrail.after_call(name, args, content, failed=True)
            content = append_guardrail_guidance(content, post)
        return _with_elapsed_ms(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            },
            started,
        )
    chat_attachments: list[dict[str, str]] = []
    try:
        result = await registry.call(name, args)
        log.info("tool_executed", tool=name)
        session_id = get_chat_session_id()
        if session_id:
            if name == "memory":
                await reset_memory_nudge(session_id)
            elif name == "skill_manage":
                await reset_skill_nudge(session_id)
        content = result.to_message()
        att = _chat_attachment_from_metadata(result.metadata)
        if att is not None:
            chat_attachments.append(att)
    except ToolError as exc:
        log.warning("tool_failed", tool=name, error=str(exc))
        content = f"Error: {exc}"
    if guardrail is not None:
        post = guardrail.after_call(
            name,
            args,
            content,
            failed=classify_tool_failure(name, content),
        )
        content = append_guardrail_guidance(content, post)
    out: dict[str, Any] = {"role": "tool", "tool_call_id": tc.id, "content": content}
    if chat_attachments:
        out["_chat_attachments"] = chat_attachments
    return _with_elapsed_ms(out, started)


async def _execute_tool_calls(
    registry: ToolRegistry,
    tool_calls: Iterable[Any],
    *,
    blocked_tool_actions: dict[str, set[str]] | None = None,
    guardrail: ToolCallGuardrailController | None = None,
) -> list[dict[str, Any]]:
    """并行执行同一轮的多个工具调用（gather 保持原顺序）。"""
    calls = list(tool_calls)
    if not calls:
        return []
    blocked_map = blocked_tool_actions or {}
    if len(calls) == 1:
        tool_name = str(getattr(calls[0].function, "name", "")).strip().lower()
        return [
            await _execute_one_tool_call(
                registry,
                calls[0],
                blocked_actions=blocked_map.get(tool_name, set()),
                guardrail=guardrail,
            )
        ]
    return list(
        await asyncio.gather(
            *(
                _execute_one_tool_call(
                    registry,
                    tc,
                    blocked_actions=blocked_map.get(
                        str(getattr(tc.function, "name", "")).strip().lower(),
                        set(),
                    ),
                    guardrail=guardrail,
                )
                for tc in calls
            )
        )
    )


def _ensure_user_visible_text(text: str, *, fallback: str) -> str:
    cleaned = str(text or "").strip()
    return cleaned or fallback


def _finalize_request_kwargs(
    *,
    model: str,
    working_messages: list[dict[str, Any]],
    extra: dict[str, Any] | None,
    notice: str,
) -> dict[str, Any]:
    req_messages = list(working_messages)
    req_messages.append({"role": "system", "content": notice})
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": req_messages,
        "tool_choice": "none",
    }
    if extra:
        for key, value in extra.items():
            if key in {"tools", "tool_choice", "stream"}:
                continue
            kwargs[key] = value
    return kwargs


async def _finalize_without_tools(
    *,
    client,
    model: str,
    working_messages: list[dict[str, Any]],
    extra: dict[str, Any] | None,
    session_id: str | None = None,
    usage_scenario: str = "chat",
    notice: str = _TOOL_ROUND_LIMIT_NOTICE,
    fallback_text: str = _TOOL_ROUND_LIMIT_FALLBACK,
) -> tuple[dict[str, Any], str, str, int]:
    kwargs = _finalize_request_kwargs(
        model=model,
        working_messages=working_messages,
        extra=extra,
        notice=notice,
    )
    completion: ChatCompletion = await client.chat.completions.create(**kwargs)
    schedule_openai_usage(
        usage=completion.usage,
        scenario=usage_scenario,
        model=model,
        session_id=session_id,
    )
    usage_tokens = int((completion.usage.total_tokens if completion.usage else 0) or 0)
    msg = completion.choices[0].message
    if getattr(msg, "tool_calls", None):
        log.warning("finalize_still_requested_tools", model=model)
        retry_kwargs = _finalize_request_kwargs(
            model=model,
            working_messages=working_messages,
            extra=extra,
            notice=notice + "\n再次强调：禁止 tool_calls，只输出用户可见正文。",
        )
        completion = await client.chat.completions.create(**retry_kwargs)
        schedule_openai_usage(
            usage=completion.usage,
            scenario=usage_scenario,
            model=model,
            session_id=session_id,
        )
        usage_tokens += int((completion.usage.total_tokens if completion.usage else 0) or 0)
        msg = completion.choices[0].message
    msg_dict = _serialize_message(msg)
    final_text = _ensure_user_visible_text(openai_message_text(msg), fallback=fallback_text)
    if not str(msg_dict.get("content") or "").strip():
        msg_dict["content"] = final_text
    return msg_dict, final_text, openai_message_reasoning(msg), usage_tokens


def _compression_preview(
    *,
    mode: str,
    before_tokens: int,
    after_tokens: int,
    summary_text: str,
) -> str:
    if summary_text:
        return (
            f"【自动上下文压缩】mode={mode}, tokens: {before_tokens} -> {after_tokens}\n\n"
            f"{summary_text}"
        )
    return (
        f"【自动上下文压缩】mode={mode}, tokens: {before_tokens} -> {after_tokens}\n"
        "本次未生成可展示摘要（已进行截断保留）。"
    )


async def _inject_todo_after_compression(
    session_id: str | None,
    working: list[dict[str, Any]],
    compression_report: dict[str, Any],
) -> None:
    if not session_id or not compression_report.get("triggered"):
        return
    from ..todos.store import COMPRESSION_TODO_INJECTION_MARKER, format_compression_injection

    for msg in reversed(working):
        if msg.get("role") == "user" and COMPRESSION_TODO_INJECTION_MARKER in str(msg.get("content") or ""):
            return

    injection = await format_compression_injection(session_id)
    if injection:
        working.append({"role": "user", "content": injection})


async def _persist_compression_if_needed(
    session_id: str | None,
    run_id: str | None,
    working: list[dict[str, Any]],
    compression_report: dict[str, Any],
) -> None:
    if not session_id or not compression_report.get("triggered"):
        return
    archive_ids = list(compression_report.get("archive_message_ids") or [])
    if not archive_ids:
        return
    summary_id = await persist_context_compression(
        session_id,
        archive_message_ids=archive_ids,
        summary_text=str(compression_report.get("summary") or ""),
        mode=str(compression_report.get("mode") or "truncate"),
        before_tokens=int(compression_report.get("before_tokens") or 0),
        after_tokens=int(compression_report.get("after_tokens") or 0),
        run_id=run_id,
    )
    if not summary_id:
        return
    for m in working:
        content = str(m.get("content") or "")
        if m.get("role") == "system" and "历史对话摘要" in content:
            m["id"] = summary_id
            break


def _select_chat_model(
    msgs: list[dict[str, Any]],
    *,
    default_model: str | None,
    main_model: str,
    vision_model: str,
) -> str:
    """角色专用模型优先；default_model 为会话默认（主模型），仅作无图时的回退。"""
    if messages_include_images(msgs):
        return vision_model
    if default_model:
        return default_model
    return main_model


async def run_chat_loop(
    messages: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    disabled_tools: set[str] | None = None,
    blocked_tool_actions: dict[str, set[str]] | None = None,
    max_rounds: int | None = None,
    usage_scenario: str = "chat",
) -> tuple[LoopResult, list[dict[str, Any]]]:
    settings = get_settings()
    main_model = await resolve_model("main")
    vision_model = await resolve_model("vision")
    compression_model = await resolve_model("compression")

    def _round_model(msgs: list[dict[str, Any]]) -> str:
        return _select_chat_model(
            msgs,
            default_model=model,
            main_model=main_model,
            vision_model=vision_model,
        )

    effective_max_rounds = max(1, max_rounds if max_rounds is not None else settings.max_loop_rounds)
    token_limit = int(_model_limit(_round_model(messages)) * settings.context_compress_ratio)
    client = get_llm_client()
    tools_schema = registry.schemas(workspace_id=get_workspace_id()) or None
    disabled = _normalize_disabled_tools(disabled_tools)
    blocked_actions = _normalize_blocked_actions(blocked_tool_actions)
    if tools_schema and disabled:
        filtered = [
            t
            for t in tools_schema
            if str(((t.get("function") or {}).get("name") or "")).strip().lower() not in disabled
        ]
        tools_schema = filtered or None
    max_tool_rounds = max(1, settings.max_tool_rounds)

    working = list(messages)
    total_tokens = 0
    tool_calls_made = 0
    tool_rounds_made = 0
    artifact_save_rounds_made = 0
    final_text = ""
    guardrail = ToolCallGuardrailController(guardrail_config_from_settings(settings))
    set_chat_session_id(session_id)

    for round_idx in range(1, effective_max_rounds + 1):
        working, compression_report = await compress_with_report(
            working,
            max_tokens=token_limit,
            client=client,
            model=compression_model,
            keep_last=settings.context_keep_last,
            min_middle=settings.context_distill_min_middle,
        )
        await _persist_compression_if_needed(session_id, run_id, working, compression_report)
        await _inject_todo_after_compression(session_id, working, compression_report)
        log.info(
            "loop_round_start",
            round=round_idx,
            messages=len(working),
            tools=len(tools_schema or []),
        )
        round_model = _round_model(working)
        kwargs: dict[str, Any] = {
            "model": round_model,
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
        schedule_openai_usage(
            usage=usage,
            scenario=usage_scenario,
            model=round_model,
            session_id=session_id,
        )

        choice = completion.choices[0]
        msg = choice.message

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            normalized_calls = _normalize_chat_tool_calls(
                msg.tool_calls,
                id_prefix=f"call-r{round_idx}",
            )
            normalized_calls = _cap_clarify_calls(normalized_calls)
            assistant_msg: dict[str, Any] = {"role": "assistant", "tool_calls": normalized_calls}
            text = openai_message_text(msg)
            reasoning = openai_message_reasoning(msg)
            if text or reasoning or getattr(msg, "content", None) is not None:
                if text:
                    assistant_msg["content"] = text
                if reasoning:
                    assistant_msg["reasoning_content"] = reasoning
            working.append(assistant_msg)
            if tool_rounds_made >= max_tool_rounds:
                log.warning(
                    "loop_tool_round_limit_reached",
                    round=round_idx,
                    tool_rounds=tool_rounds_made,
                    max_tool_rounds=max_tool_rounds,
                )
                final_msg, final_text, final_reasoning, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=_round_model(working),
                    working_messages=working,
                    extra=extra,
                    session_id=session_id,
                    usage_scenario=usage_scenario,
                )
                total_tokens += more_tokens
                working.append(final_msg)
                return (
                    LoopResult(
                        final_text=final_text,
                        rounds=round_idx,
                        total_tokens=total_tokens,
                        tool_calls_made=tool_calls_made,
                        final_reasoning=final_reasoning,
                    ),
                    working,
                )
            tool_rounds_made += 1
            tool_calls_made += len(normalized_calls)
            stub_calls = [_ToolCallStub(raw) for raw in normalized_calls]
            if _all_calls_are(stub_calls, "artifact_save") and artifact_save_rounds_made >= 1:
                final_msg, final_text, final_reasoning, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=_round_model(working),
                    working_messages=working,
                    extra=extra,
                    session_id=session_id,
                    usage_scenario=usage_scenario,
                    notice=_ARTIFACT_SAVE_LOOP_NOTICE,
                    fallback_text="已保存。",
                )
                total_tokens += more_tokens
                working.append(final_msg)
                return (
                    LoopResult(
                        final_text=final_text or "已保存。",
                        rounds=round_idx,
                        total_tokens=total_tokens,
                        tool_calls_made=tool_calls_made,
                        final_reasoning=final_reasoning,
                    ),
                    working,
                )
            tool_results = await _execute_tool_calls(
                registry,
                stub_calls,
                blocked_tool_actions=blocked_actions,
                guardrail=guardrail,
            )
            working.extend(_tool_message_for_llm(r) for r in tool_results)
            stop = guardrail.turn_stop_decision
            if stop is not None and stop.should_stop_turn:
                halt = stop
                log.warning("tool_guardrail_halt", code=halt.code, tool=halt.tool_name, count=halt.count)
                final_msg, final_text, final_reasoning, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=_round_model(working),
                    working_messages=working,
                    extra=extra,
                    session_id=session_id,
                    usage_scenario=usage_scenario,
                    notice=_TOOL_GUARDRAIL_HALT_NOTICE,
                    fallback_text=halt.message or _TOOL_ROUND_LIMIT_FALLBACK,
                )
                total_tokens += more_tokens
                working.append(final_msg)
                return (
                    LoopResult(
                        final_text=final_text,
                        rounds=round_idx,
                        total_tokens=total_tokens,
                        tool_calls_made=tool_calls_made,
                        final_reasoning=final_reasoning,
                    ),
                    working,
                )
            if _all_calls_are(stub_calls, "artifact_save"):
                artifact_save_rounds_made += 1
            # clarify 成功时才终结本轮，失败则把 tool 错误回给模型并重试
            if _clarify_succeeded(stub_calls, tool_results):
                return (
                    LoopResult(
                        final_text=openai_message_text(msg),
                        rounds=round_idx,
                        total_tokens=total_tokens,
                        tool_calls_made=tool_calls_made,
                        final_reasoning=openai_message_reasoning(msg),
                    ),
                    working,
                )
            continue

        working.append(_serialize_message(msg))
        final_text = openai_message_text(msg)
        log.info("loop_finished", round=round_idx, tokens=total_tokens)
        return (
            LoopResult(
                final_text=final_text,
                rounds=round_idx,
                total_tokens=total_tokens,
                tool_calls_made=tool_calls_made,
                final_reasoning=openai_message_reasoning(msg),
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
            final_reasoning="",
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
    session_id: str | None = None,
    run_id: str | None = None,
    disabled_tools: set[str] | None = None,
    blocked_tool_actions: dict[str, set[str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式 chat loop。

    yield 事件类型：
    - {"type": "reasoning_delta", "content": str}             思考链增量
    - {"type": "delta", "content": str}                       正文增量
    - {"type": "tool_call", "name": str, "id": str, "arguments": str}  工具开始
    - {"type": "tool_result", "tool_call_id": str, "preview": str}
    - {"type": "done", "final_text", "final_reasoning", "rounds", "total_tokens", "tool_calls_made"}
    """
    settings = get_settings()
    main_model = await resolve_model("main")
    vision_model = await resolve_model("vision")
    compression_model = await resolve_model("compression")

    def _round_model(msgs: list[dict[str, Any]]) -> str:
        return _select_chat_model(
            msgs,
            default_model=model,
            main_model=main_model,
            vision_model=vision_model,
        )

    max_rounds = settings.max_loop_rounds
    token_limit = int(_model_limit(_round_model(messages)) * settings.context_compress_ratio)
    client = get_llm_client()
    tools_schema = registry.schemas(workspace_id=get_workspace_id()) or None
    disabled = _normalize_disabled_tools(disabled_tools)
    blocked_actions = _normalize_blocked_actions(blocked_tool_actions)
    if tools_schema and disabled:
        filtered = [
            t
            for t in tools_schema
            if str(((t.get("function") or {}).get("name") or "")).strip().lower() not in disabled
        ]
        tools_schema = filtered or None
    max_tool_rounds = max(1, settings.max_tool_rounds)

    working = list(messages)
    total_tokens = 0
    tool_calls_made = 0
    tool_rounds_made = 0
    artifact_save_rounds_made = 0
    final_text = ""
    guardrail = ToolCallGuardrailController(guardrail_config_from_settings(settings))
    stream_max_duration = (
        settings.stream_max_duration_s if settings.stream_max_duration_s > 0 else None
    )
    set_chat_session_id(session_id)

    for round_idx in range(1, max_rounds + 1):
        working, compression_report = await compress_with_report(
            working,
            max_tokens=token_limit,
            client=client,
            model=compression_model,
            keep_last=settings.context_keep_last,
            min_middle=settings.context_distill_min_middle,
        )
        await _persist_compression_if_needed(session_id, run_id, working, compression_report)
        if compression_report.get("triggered"):
            call_id = f"auto-summarize-r{round_idx}"
            mode = str(compression_report.get("mode") or "truncate")
            before_tokens = int(compression_report.get("before_tokens") or 0)
            after_tokens = int(compression_report.get("after_tokens") or 0)
            summary_text = str(compression_report.get("summary") or "").strip()
            tool_content = _compression_preview(
                mode=mode,
                before_tokens=before_tokens,
                after_tokens=after_tokens,
                summary_text=summary_text,
            )
            yield {
                "type": "tool_call",
                "name": "summarize",
                "id": call_id,
                "ephemeral": True,
            }
            yield {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": "summarize",
                "preview": tool_content,
                "content": tool_content,
                "ephemeral": True,
            }
        await _inject_todo_after_compression(session_id, working, compression_report)
        log.info(
            "loop_round_start",
            round=round_idx,
            messages=len(working),
            tools=len(tools_schema or []),
            stream=True,
        )
        kwargs: dict[str, Any] = {
            "model": _round_model(working),
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
        accum_reasoning = ""
        accum_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        round_usage: Any = None

        try:
            monitored = iter_with_stream_health(
                stream,
                chunk_timeout_s=settings.stream_chunk_timeout_s,
                max_total_s=stream_max_duration,
            )
            async for event in monitored:
                if event.usage:
                    round_usage = event.usage
                    total_tokens += event.usage.total_tokens or 0
                if not event.choices:
                    continue
                choice = event.choices[0]
                delta = choice.delta
                if delta is not None:
                    reasoning_piece = openai_delta_reasoning(delta)
                    if reasoning_piece:
                        accum_reasoning += reasoning_piece
                        yield {"type": "reasoning_delta", "content": reasoning_piece}
                    content_piece = openai_delta_content(delta)
                    if content_piece:
                        accum_content += content_piece
                        yield {"type": "delta", "content": content_piece}
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
        except StreamHealthError as exc:
            log.warning("stream_health_abort", code=exc.code, error=str(exc), round=round_idx)
            raise

        schedule_openai_usage(
            usage=round_usage,
            scenario="chat",
            model=kwargs["model"],
            session_id=session_id,
        )

        normalized_tool_calls: list[dict[str, Any]] = []
        if accum_tool_calls:
            sorted_idx = sorted(accum_tool_calls)
            for pos, idx in enumerate(sorted_idx):
                raw = dict(accum_tool_calls[idx])
                if not str(raw.get("id") or "").strip():
                    raw["id"] = f"call-r{round_idx}-{pos}"
                normalized_tool_calls.append(raw)
        normalized_tool_calls = _cap_clarify_calls(normalized_tool_calls)

        msg_dict = assistant_message_dict(
            content=accum_content,
            reasoning_content=accum_reasoning,
            tool_calls=normalized_tool_calls or None,
        )
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
                final_msg, capped_text, capped_reasoning, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=_round_model(working),
                    working_messages=working,
                    extra=extra,
                    session_id=session_id,
                )
                total_tokens += more_tokens
                working.append(final_msg)
                yield {"type": "delta", "content": capped_text}
                final_text = capped_text
                yield {
                    "type": "done",
                    "final_text": final_text,
                    "final_reasoning": capped_reasoning,
                    "rounds": round_idx,
                    "total_tokens": total_tokens,
                    "tool_calls_made": tool_calls_made,
                }
                return
            tool_rounds_made += 1
            tool_calls_made += len(normalized_tool_calls)
            stub_calls = [_ToolCallStub(raw) for raw in normalized_tool_calls]
            if _all_calls_are(stub_calls, "artifact_save") and artifact_save_rounds_made >= 1:
                final_msg, capped_text, capped_reasoning, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=_round_model(working),
                    working_messages=working,
                    extra=extra,
                    session_id=session_id,
                    notice=_ARTIFACT_SAVE_LOOP_NOTICE,
                    fallback_text="已保存。",
                )
                total_tokens += more_tokens
                working.append(final_msg)
                yield {"type": "delta", "content": capped_text}
                final_text = capped_text
                yield {
                    "type": "done",
                    "final_text": final_text,
                    "final_reasoning": capped_reasoning,
                    "rounds": round_idx,
                    "total_tokens": total_tokens,
                    "tool_calls_made": tool_calls_made,
                }
                return
            yield {"type": "assistant_tools", "message": msg_dict}
            for stub in stub_calls:
                yield {"type": "tool_call", "name": stub.function.name, "id": stub.id, "arguments": stub.function.arguments}
            tool_results = await _execute_tool_calls(
                registry,
                stub_calls,
                blocked_tool_actions=blocked_actions,
                guardrail=guardrail,
            )
            for stub, r in zip(stub_calls, tool_results):
                preview = r.get("content") or ""
                yield {
                    "type": "tool_result",
                    "tool_call_id": r["tool_call_id"],
                    "name": stub.function.name,
                    "preview": preview,
                    "content": r.get("content") or "",
                    "elapsed_ms": r.get("_elapsed_ms"),
                }
                for att in r.get("_chat_attachments") or []:
                    yield {"type": "attachment", "id": att["id"], "name": att["name"]}
            working.extend(_tool_message_for_llm(r) for r in tool_results)
            stop = guardrail.turn_stop_decision
            if stop is not None and stop.should_stop_turn:
                halt = stop
                log.warning(
                    "tool_guardrail_halt",
                    code=halt.code,
                    tool=halt.tool_name,
                    count=halt.count,
                    stream=True,
                )
                final_msg, capped_text, capped_reasoning, more_tokens = await _finalize_without_tools(
                    client=client,
                    model=_round_model(working),
                    working_messages=working,
                    extra=extra,
                    session_id=session_id,
                    notice=_TOOL_GUARDRAIL_HALT_NOTICE,
                    fallback_text=halt.message or _TOOL_ROUND_LIMIT_FALLBACK,
                )
                total_tokens += more_tokens
                working.append(final_msg)
                yield {"type": "delta", "content": capped_text}
                final_text = capped_text
                yield {
                    "type": "done",
                    "final_text": final_text,
                    "final_reasoning": capped_reasoning,
                    "rounds": round_idx,
                    "total_tokens": total_tokens,
                    "tool_calls_made": tool_calls_made,
                }
                return
            if _all_calls_are(stub_calls, "artifact_save"):
                artifact_save_rounds_made += 1
            # clarify 成功时才终结本轮，失败则把 tool 错误回给模型并重试
            if _clarify_succeeded(stub_calls, tool_results):
                yield {
                    "type": "done",
                    "final_text": accum_content,
                    "final_reasoning": accum_reasoning,
                    "rounds": round_idx,
                    "total_tokens": total_tokens,
                    "tool_calls_made": tool_calls_made,
                }
                return
            continue

        log.info("loop_finished", round=round_idx, tokens=total_tokens, stream=True)
        yield {
            "type": "done",
            "final_text": accum_content,
            "final_reasoning": accum_reasoning,
            "rounds": round_idx,
            "total_tokens": total_tokens,
            "tool_calls_made": tool_calls_made,
        }
        return

    log.warning("loop_max_rounds_exceeded", rounds=max_rounds, stream=True)
    yield {
        "type": "done",
        "final_text": final_text or "[max rounds reached]",
        "final_reasoning": "",
        "rounds": max_rounds,
        "total_tokens": total_tokens,
        "tool_calls_made": tool_calls_made,
    }
