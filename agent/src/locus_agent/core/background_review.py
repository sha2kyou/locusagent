"""Background Self-Improvement Review — 对话结束后 fork 子循环沉淀 memory / skill。

触发策略（保守，降低噪音）：
- memory review：每 N 个用户轮次（默认 20）
- skill review：loop_rounds 累加达阈值（默认 24）且在 turn 末尾触发
- 前台 memory / skill_manage 调用会重置对应计数器
- 默认倾向「无需保存」，仅在明确信号时写入
"""

from __future__ import annotations

import copy
import json
from typing import Any

from ..config import get_settings
from ..host_notify import notify_background_review
from ..logging import get_logger
from .write_origin import ORIGIN_AUTO_EXTRACT, write_origin_scope
from ..tools import ToolRegistry, registry as default_registry
from .loop import run_chat_loop
from .models import resolve_model
from .session_review_state import assess_turn_end_review_triggers, flush_disabled_review_state
from .system_prompt import assemble_system_prompt, get_cached_stable_context

log = get_logger("background_review")

_REVIEW_ALLOWED_TOOLS = frozenset({"skill_view", "skill_manage", "memory"})

_REVIEW_SYSTEM_PROMPT = (
    "You are AgentPod's background self-improvement reviewer. You receive a completed conversation "
    "trajectory and decide whether to update long-term memory or the private skill library. "
    "You may only call skill_view, skill_manage, memory. "
    "Shared and built-in skills are read-only; only private skills may be created, patched, or deleted. "
    "Default conclusion should be nothing to save—write only when there is a clear, long-reusable signal."
)

_MEMORY_REVIEW_PROMPT = (
    "Review the conversation above and decide whether to write to long-term memory.\n\n"
    "Write only if one of these holds:\n"
    "1. The user explicitly shared stable identity, preferences, or long-term constraints (not a one-off task).\n"
    "2. The user expressed ongoing expectations for your behavior or workflow (e.g. always..., by default...).\n\n"
    "Use memory(action=add|replace): term=long_term for stable user facts/preferences (long-term memory), "
    "term=short_term for persistent operational notes (short-term memory). "
    "For replace, pass id and content from the snapshot (full new text); without id use old_text.\n"
    "Do not save: one-off Q&A, task progress, temporary data, table/document summaries, workflow knowledge "
    "that belongs in skills. Information stale within seven days should not go to memory.\n"
    "Write memories as declarative facts, not instructions to yourself.\n"
    "If there is no clear long-term value, reply Nothing to save. and stop."
)

_SKILL_REVIEW_PROMPT = (
    "Review the conversation above and decide whether to update the private skill library.\n\n"
    "Default reply Nothing to save.—only skill_manage when these clear signals appear:\n"
    "  • The user explicitly corrected style, tone, format, verbosity, or workflow (e.g. don't..., too verbose, just answer).\n"
    "  • A non-trivial technique reusable across similar tasks appeared, and the user did not object to saving it.\n"
    "  • A private skill read via skill_view was wrong or incomplete and this session validated a fix.\n\n"
    "Do not create skills just because many tools were used or the session was long.\n"
    "Target shape: class-level private skills, not one skill per session.\n"
    "Prefer patching existing private skills (skill_view first); create only when none fit and reuse value is clear.\n"
    "Protected skills (do not edit): skills under built-in and shared skill directories.\n"
    "Do not save as skills: transient env failures, negative tool assertions, one-off task narratives, table/document conclusions.\n"
    "When the session went smoothly with no corrections and no user-approved reusable technique, "
    "you must reply Nothing to save."
)

_COMBINED_REVIEW_PROMPT = (
    "Review the conversation above and decide whether to update memory and/or private skills.\n\n"
    "Default Nothing to save.—act only when signals are clear.\n\n"
    "Memory: stable user facts/preferences/ongoing expectations only. Skip task progress, document content, temporary conclusions.\n"
    "Skills: user corrections or reusable workflow techniques only; do not update by default for tool-heavy sessions. "
    "Shared and built-in skills are read-only.\n\n"
    "If neither dimension needs an update, reply Nothing to save. and stop."
)

_TOOL_RESTRICTION_NOTICE = (
    "\n\nYou may only call skill_view, skill_manage, memory. "
    "Other tools are unavailable—do not attempt them."
)

_REVIEW_ACTION_TOOLS = frozenset({"memory", "skill_manage"})


def _review_disabled_tools(registry: ToolRegistry) -> set[str]:
    return {t.name for t in registry.all() if t.name not in _REVIEW_ALLOWED_TOOLS}


def _last_user_index(messages: list[dict[str, Any]]) -> int:
    last = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last = i
    return last


def _current_turn_snapshot(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = _last_user_index(messages)
    if start < 0:
        return []
    out: list[dict[str, Any]] = []
    for msg in messages[start:]:
        if not isinstance(msg, dict) or msg.get("role") == "system":
            continue
        cleaned = {k: v for k, v in msg.items() if k != "id"}
        out.append(cleaned)
    return out


def _prior_tool_contents(messages: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            out.add(content.strip())
    return out


def _prior_tool_call_ids(messages: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        tcid = str(msg.get("tool_call_id") or "").strip()
        if tcid:
            out.add(tcid)
    return out


def _tool_names_by_call_id(messages: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            call_id = str(tc.get("id") or "").strip()
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "").strip()
            if call_id and name:
                mapping[call_id] = name
    return mapping


def _is_review_noop_content(content: str) -> bool:
    text = str(content or "").strip()
    normalized = text.lower()
    return normalized in {"nothing to save.", "nothing to save"} or text in {"无需保存。", "无需保存"}


def _summarize_from_json_tool_result(content: str) -> str | None:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    message = str(data.get("message") or "").strip()
    if message:
        return message
    target = str(data.get("target") or "").strip()
    if target:
        return f"{target} updated"
    return None


def summarize_background_review_actions(
    review_messages: list[dict[str, Any]],
    prior_snapshot: list[dict[str, Any]],
) -> list[str]:
    prior_contents = _prior_tool_contents(prior_snapshot)
    prior_call_ids = _prior_tool_call_ids(prior_snapshot)
    tool_names = _tool_names_by_call_id(review_messages)
    actions: list[str] = []
    for msg in review_messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "").strip()
        if not content or content in prior_contents:
            continue
        call_id = str(msg.get("tool_call_id") or "").strip()
        if call_id and call_id in prior_call_ids:
            continue
        if content.startswith("Error:") or content.startswith("error:"):
            continue
        if _is_review_noop_content(content):
            continue
        tool_name = tool_names.get(call_id, "")
        if tool_name not in _REVIEW_ACTION_TOOLS:
            continue
        summary = _summarize_from_json_tool_result(content)
        actions.append(summary or content)
    return list(dict.fromkeys(actions))


async def assess_background_review_triggers(
    *,
    session_id: str,
    loop_rounds: int,
) -> tuple[bool, bool]:
    """轮次结束时评估 (review_memory, review_skills)。"""
    settings = get_settings()
    if not settings.background_review_enabled:
        await flush_disabled_review_state(session_id)
        return False, False
    return await assess_turn_end_review_triggers(session_id, loop_rounds=loop_rounds)


async def should_run_background_review(
    *,
    loop_rounds: int,
    session_id: str | None = None,
) -> bool:
    if not session_id:
        return False
    review_memory, review_skills = await assess_background_review_triggers(
        session_id=session_id,
        loop_rounds=loop_rounds,
    )
    return review_memory or review_skills


def _select_review_prompt(*, review_memory: bool, review_skills: bool) -> str:
    if review_memory and review_skills:
        return _COMBINED_REVIEW_PROMPT
    if review_memory:
        return _MEMORY_REVIEW_PROMPT
    return _SKILL_REVIEW_PROMPT


async def run_background_review(
    messages: list[dict[str, Any]],
    *,
    review_memory: bool,
    review_skills: bool,
    model: str | None = None,
    session_id: str | None = None,
    registry: ToolRegistry | None = None,
) -> list[str]:
    if not review_memory and not review_skills:
        return []

    snapshot = _current_turn_snapshot(messages)
    if not snapshot:
        return []

    settings = get_settings()
    reg = registry or default_registry
    review_model = model or await resolve_model("skill_reflect")
    prompt = _select_review_prompt(review_memory=review_memory, review_skills=review_skills)
    prior_snapshot = copy.deepcopy(snapshot)

    inherited = await get_cached_stable_context(session_id) if session_id else None
    inherited_text = assemble_system_prompt(inherited) if inherited else ""

    system_messages: list[dict[str, Any]] = []
    if inherited_text:
        system_messages.append({"role": "system", "content": inherited_text})
    system_messages.append({"role": "system", "content": _REVIEW_SYSTEM_PROMPT})

    loop_messages: list[dict[str, Any]] = [
        *system_messages,
        *snapshot,
        {"role": "user", "content": prompt + _TOOL_RESTRICTION_NOTICE},
    ]

    try:
        with write_origin_scope(ORIGIN_AUTO_EXTRACT):
            _result, final_messages = await run_chat_loop(
                loop_messages,
                registry=reg,
                model=review_model,
                session_id=None,
                run_id=None,
                disabled_tools=_review_disabled_tools(reg),
                max_rounds=settings.background_review_max_rounds,
                usage_scenario="skill_reflect",
            )
    except Exception as exc:
        log.warning("background_review_failed", error=str(exc))
        return []

    actions = summarize_background_review_actions(final_messages, prior_snapshot)
    if actions:
        summary = " · ".join(actions)
        log.info(
            "background_review_applied",
            summary=summary,
            review_memory=review_memory,
            review_skills=review_skills,
            session_id=session_id or "",
        )
        if session_id:
            await notify_background_review(summary=summary, session_id=session_id)
    else:
        log.info(
            "background_review_noop",
            review_memory=review_memory,
            review_skills=review_skills,
            session_id=session_id or "",
        )
    return actions
