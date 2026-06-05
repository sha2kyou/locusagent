"""Background Self-Improvement Review — 对话结束后 fork 子循环沉淀 memory / skill。

对齐 Hermes background_review：回放本轮轨迹，仅开放 memory + skill 工具，
由辅助模型决定是否 create/patch skill 或写入 memory。失败安全，不影响主响应。
"""

from __future__ import annotations

import copy
from typing import Any

from ..config import get_settings
from ..host_notify import notify_background_review
from ..logging import get_logger
from .write_origin import ORIGIN_AUTO_EXTRACT, write_origin_scope
from ..tools import ToolRegistry, registry as default_registry
from .loop import run_chat_loop
from .models import resolve_model

log = get_logger("background_review")

_REVIEW_ALLOWED_TOOLS = frozenset({"skill_view", "skill_manage", "memory"})

_REVIEW_SYSTEM_PROMPT = (
    "你是 AgentPod 的后台自我改进审查器。你会收到一段已完成的对话轨迹，"
    "任务是根据用户指令判断是否需要更新长期记忆或私有技能库。"
    "你只能调用 skill_view、skill_manage、memory。"
    "public 技能只读，不可修改；仅 private 技能可 create/patch/delete。"
)

_MEMORY_REVIEW_PROMPT = (
    "Review the conversation above and consider saving to memory if appropriate.\n\n"
    "Focus on:\n"
    "1. Has the user revealed persona, preferences, or personal details worth remembering?\n"
    "2. Has the user expressed expectations about how you should behave or work?\n\n"
    "Use memory(action=add|replace) with target=user for stable user facts/preferences, "
    "target=memory for durable operational notes. "
    "For replace, pass id from the snapshot plus content (full new text); old_text works when id is unavailable. "
    "Do not save one-off Q&A, task progress, or workflow knowledge that belongs in skills.\n"
    "If nothing is worth saving, reply 'Nothing to save.' and stop."
)

_SKILL_REVIEW_PROMPT = (
    "Review the conversation above and update the private skill library. Be ACTIVE — "
    "most tool-heavy sessions produce at least one skill update, even if small.\n\n"
    "Signals (any one warrants action):\n"
    "  • User corrected style, tone, format, verbosity, workflow, or approach.\n"
    "  • Non-trivial technique, fix, workaround, or debugging path emerged.\n"
    "  • A skill consulted via skill_view turned out wrong, incomplete, or outdated.\n\n"
    "Preference order:\n"
    "  1. PATCH an existing private skill that covers this class of task (skill_view first).\n"
    "  2. CREATE a new class-level private skill when nothing fits — name must be generic "
    "(not PR numbers, error strings, or one-off session titles).\n\n"
    "Do NOT capture: missing binaries, transient env errors, 'tool X is broken' claims, "
    "or one-off task narratives.\n"
    "Public/bundled skills are read-only — if only they need changes, say 'Nothing to save.' "
    "and stop.\n"
    "Otherwise act with skill_manage."
)

_COMBINED_REVIEW_PROMPT = (
    "Review the conversation above and update memory and/or private skills.\n\n"
    "**Memory**: save durable user facts/preferences (target=user) or operational notes "
    "(target=memory). Skip one-off Q&A and workflow knowledge that belongs in skills.\n\n"
    "**Skills**: be ACTIVE — patch existing private skills first; create class-level private "
    "skills only when needed. Public skills are read-only.\n\n"
    "Do NOT capture environment glitches, negative tool claims, or one-off tasks as skills.\n"
    "If genuinely nothing on either dimension, say 'Nothing to save.' and stop."
)

_TOOL_RESTRICTION_NOTICE = (
    "\n\nYou may only call skill_view, skill_manage, and memory. "
    "Other tools are unavailable — do not attempt them."
)

_REVIEW_ACTION_TOOLS = frozenset({"memory", "skill_manage"})

_REVIEW_TRIGGER_SYSTEM_PROMPT = (
    "你是后台学习触发分类器。根据本轮用户请求与工具活动摘要，判断值不值得启动 memory/skill 后台审查，"
    "从对话中沉淀可复用的用户偏好或工作流经验。\n\n"
    "should_review=true：用户透露稳定偏好/身份/约束、纠正行为方式、出现可复用技巧或流程改进信号、"
    "或工具密集执行且可能有经验可沉淀。\n"
    "should_review=false：纯问答/翻译/总结、一次性小任务、无 durable 信息、"
    "或明显只是临时排障且无可复用模式。\n\n"
    '输出严格 JSON：{"should_review": true|false, "reason": "一句中文说明"}'
)


def _review_disabled_tools(registry: ToolRegistry) -> set[str]:
    return {t.name for t in registry.all() if t.name not in _REVIEW_ALLOWED_TOOLS}


def _strip_system_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]


def _last_user_index(messages: list[dict[str, Any]]) -> int:
    last = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last = i
    return last


def _current_turn_snapshot(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """提取本轮对话（最后一条 user 起），并去掉 DB id 避免压缩副作用。"""
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


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "input_text"}:
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _last_user_query(messages: list[dict[str, Any]]) -> str:
    start = _last_user_index(messages)
    if start < 0:
        return ""
    msg = messages[start]
    if not isinstance(msg, dict):
        return ""
    return _message_text(msg.get("content"))


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
    text = str(content or "").strip().lower()
    return text in {"nothing to save.", "nothing to save"}


def summarize_background_review_actions(
    review_messages: list[dict[str, Any]],
    prior_snapshot: list[dict[str, Any]],
) -> list[str]:
    """从 review 循环的 memory/skill_manage 成功 tool 消息中提取用户可见摘要。"""
    prior = _prior_tool_contents(prior_snapshot)
    tool_names = _tool_names_by_call_id(review_messages)
    actions: list[str] = []
    for msg in review_messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "").strip()
        if not content or content in prior:
            continue
        if content.startswith("Error:") or content.startswith("error:"):
            continue
        if _is_review_noop_content(content):
            continue
        call_id = str(msg.get("tool_call_id") or "").strip()
        tool_name = tool_names.get(call_id, "")
        if tool_name not in _REVIEW_ACTION_TOOLS:
            continue
        actions.append(content)
    return list(dict.fromkeys(actions))


def _turn_used_skill_manage(messages: list[dict[str, Any]]) -> bool:
    start = _last_user_index(messages)
    if start < 0:
        return False
    for msg in messages[start:]:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if str(fn.get("name") or "") == "skill_manage":
                return True
    return False


async def assess_background_review_intent(
    *,
    user_query: str,
    tool_calls_made: int,
    session_id: str | None = None,
) -> bool:
    query = str(user_query or "").strip()
    if not query:
        return False

    from .llm_classifier import classify_json

    payload = (
        f"用户请求：{query[:1500]}\n"
        f"本轮工具调用次数：{tool_calls_made}"
    )
    try:
        parsed = await classify_json(
            system_prompt=_REVIEW_TRIGGER_SYSTEM_PROMPT,
            user_content=payload,
            scenario="background_review_intent",
            session_id=session_id,
            retry_log_event="background_review_intent_disable_thinking_retry",
        )
        should_review = bool(parsed.get("should_review", False))
        log.info(
            "background_review_intent_assessed",
            should_review=should_review,
            reason=str(parsed.get("reason") or "")[:120],
            session_id=session_id,
        )
        return should_review
    except Exception as exc:
        log.warning("background_review_intent_failed", error=str(exc), session_id=session_id)
        return True


async def should_run_background_review(
    *,
    tool_calls_made: int,
    messages: list[dict[str, Any]],
    session_id: str | None = None,
) -> bool:
    """tool 活动达到阈值且前台未手动 skill_manage 时，由 LLM 判断是否触发 review。"""
    settings = get_settings()
    if not settings.background_review_enabled:
        return False
    if settings.background_review_min_tool_calls <= 0:
        return False
    if tool_calls_made < settings.background_review_min_tool_calls:
        return False
    if _turn_used_skill_manage(messages):
        return False
    return await assess_background_review_intent(
        user_query=_last_user_query(messages),
        tool_calls_made=tool_calls_made,
        session_id=session_id,
    )


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
    """Fork 受限工具循环执行 review；返回操作摘要列表（可为空）。"""
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
    loop_messages: list[dict[str, Any]] = [
        {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
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
        log.info("background_review_applied", summary=summary, session_id=session_id or "")
        if session_id:
            await notify_background_review(summary=summary, session_id=session_id)
    else:
        log.info("background_review_noop", session_id=session_id or "")
    return actions
