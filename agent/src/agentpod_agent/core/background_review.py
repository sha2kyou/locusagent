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
    "你是 AgentPod 的后台自我改进审查器。你会收到一段已完成的对话轨迹，"
    "任务是根据对话判断是否需要更新长期记忆或私有技能库。"
    "你只能调用 skill_view、skill_manage、memory。"
    "共享与内置技能只读，不可修改；仅私有技能可创建、修补或删除。"
    "默认结论应为「无需保存」——只有出现明确、可长期复用的信号时才写入。"
)

_MEMORY_REVIEW_PROMPT = (
    "请审查上方对话，判断是否应将信息写入长期记忆。\n\n"
    "仅当满足以下条件之一才写入：\n"
    "1. 用户明确透露了稳定的身份、偏好或长期约束（非一次性任务描述）。\n"
    "2. 用户明确表达了对你行为或工作方式的持续期望（如「以后都…」「默认…」）。\n\n"
    "使用 memory(action=add|replace)：term=long_term 存稳定用户事实/偏好（长期记忆），"
    "term=short_term 存持久操作笔记（短期记忆）。兼容 target=user/memory。"
    "replace 时传入快照中的 id 与 content（完整新文本）；无 id 时可用 old_text。\n"
    "不要保存：一次性问答、任务进度、临时数据、表格/文档内容摘要、应写入技能的工作流知识。"
    "七天内会过时的信息不应写入记忆。\n"
    "以陈述性事实书写记忆，不要写成给自己的指令。\n"
    "若无明确长期价值，回复「无需保存。」并结束。"
)

_SKILL_REVIEW_PROMPT = (
    "请审查上方对话，判断是否应更新私有技能库。\n\n"
    "默认回复「无需保存。」——仅在出现以下明确信号时才 skill_manage：\n"
    "  • 用户明确纠正了风格、语气、格式、冗长度或工作流（如「别…」「太啰嗦」「直接给答案」）。\n"
    "  • 出现了可复用到同类任务的非平凡技巧，且用户未明确反对沉淀。\n"
    "  • 通过 skill_view 查阅的私有技能被证明错误或不完整，且本会话已验证修正方案。\n\n"
    "不要因「工具用得多」或「会话较长」就创建技能。\n"
    "目标形态：类级别的私有技能，不要「一会话一技能」。\n"
    "优先修补现有私有技能（先 skill_view）；无合适技能且确有长期复用价值时再创建。\n"
    "受保护技能（禁止编辑）：内置与共享技能目录下的技能。\n"
    "不要沉淀为技能：环境偶发失败、工具负面断言、一次性任务叙事、表格/文档解读结论。\n"
    "会话顺利、无纠正且无经用户认可的可复用技巧时，必须回复「无需保存。」"
)

_COMBINED_REVIEW_PROMPT = (
    "请审查上方对话，判断是否更新记忆和/或私有技能。\n\n"
    "默认「无需保存。」仅在信号明确时行动。\n\n"
    "记忆：仅稳定用户事实/偏好/持续期望。跳过任务进度、文档内容、临时结论。\n"
    "技能：仅用户纠正或可复用工作流技巧；不因工具密集而默认更新。共享与内置技能只读。\n\n"
    "若无两个维度的明确更新，回复「无需保存。」并结束。"
)

_TOOL_RESTRICTION_NOTICE = (
    "\n\n你只能调用 skill_view、skill_manage、memory。"
    "其他工具不可用——请勿尝试。"
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
