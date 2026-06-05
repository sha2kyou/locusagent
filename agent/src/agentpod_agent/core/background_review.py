"""Background Self-Improvement Review — 对话结束后 fork 子循环沉淀 memory / skill。

对齐 Hermes background_review：
- memory review：每 N 个用户轮次（turn 开头计数，默认 10）
- skill review：每轮 loop_rounds 累加，达阈值（默认 10）在 turn 末尾触发
- 前台 memory / skill_manage 调用会重置对应计数器
- 无 LLM 意图分类器兜底（Hermes 纯周期触发）
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
)

_MEMORY_REVIEW_PROMPT = (
    "请审查上方对话，判断是否应将信息写入长期记忆。\n\n"
    "重点关注：\n"
    "1. 用户是否透露了值得记住的人设、偏好或个人细节？\n"
    "2. 用户是否表达了对你行为或工作方式的期望？\n\n"
    "使用 memory(action=add|replace)：target=user 存稳定用户事实/偏好，target=memory 存持久操作笔记。"
    "replace 时传入快照中的 id 与 content（完整新文本）；无 id 时可用 old_text。\n"
    "不要保存一次性问答、任务进度、合并请求或议题编号、提交哈希，或应写入技能的工作流知识。"
    "一周内会过时的信息不应写入记忆。\n"
    "以陈述性事实书写记忆，不要写成给自己的指令。\n"
    "若无值得保存的内容，回复「无需保存。」并结束。"
)

_SKILL_REVIEW_PROMPT = (
    "请审查上方对话并更新私有技能库。应积极主动——多数工具密集会话至少应产生一次技能更新，哪怕很小。"
    "空跑不是中性结果，而是错失学习机会。\n\n"
    "目标形态：类级别的私有技能，配有完整的技能文档，不要做成「一会话一技能」的扁平列表。\n\n"
    "触发信号（满足任一即应行动）：\n"
    "  • 用户纠正了风格、语气、格式、冗长度、工作流或方法。"
    "如「别再做某事」「太啰嗦」「直接给答案」等挫败反馈是一等技能信号，"
    "应将偏好嵌入治理该任务类型的技能。\n"
    "  • 出现了非平凡技巧、修复、变通方案或排查路径。\n"
    "  • 通过 skill_view 查阅的技能被证明错误、不完整或过时。\n\n"
    "优先顺序：\n"
    "  1. 修补覆盖该类任务的现有私有技能（先 skill_view）。\n"
    "  2. 无合适技能时创建新的类级别私有技能，名称须通用"
    "（不要用合并请求号、错误字符串或一次性会话标题）。\n\n"
    "用户偏好嵌入：用户抱怨你处理某类任务的方式时，应更新治理该任务的技能，"
    "仅靠 memory 不够。记忆描述用户是谁；技能描述如何为该用户完成该类任务。\n\n"
    "受保护技能（禁止编辑）：/app/skills 下的共享与内置技能。\n"
    "不要沉淀为技能：\n"
    "  • 环境依赖型失败（缺二进制、未配置凭据）。\n"
    "  • 对工具的负面断言（「某工具坏了」）。\n"
    "  • 一次性任务叙事。\n"
    "若工具因配置失败，应在现有排障技能下记录修复方法，"
    "不要把「此工具不可用」单独写成约束。\n"
    "会话顺利、无纠正且无新技巧时，「无需保存。」是合理回复，"
    "但不要将其当作默认；否则应通过 skill_manage 行动。"
)

_COMBINED_REVIEW_PROMPT = (
    "请审查上方对话，更新记忆和/或私有技能。\n\n"
    "记忆：用户是谁——人设、偏好、个人细节、行为期望。"
    "target=user 存稳定用户事实；target=memory 存持久操作笔记。"
    "跳过一次性问答、任务进度及应属于技能的工作流知识。\n\n"
    "技能：如何完成该类任务。应积极主动，多数工具密集会话值得更新。"
    "优先修补现有私有技能；仅在必要时创建类级别私有技能。共享与内置技能只读。\n\n"
    "技能信号（满足任一即可）：用户纠正风格、格式或工作流；出现非平凡技巧；"
    "查阅的技能错误或过时。\n\n"
    "优先顺序：其一，修补本会话通过 skill_view 加载过的技能；"
    "其二，修补现有综合技能；其三，创建新的类级别私有技能。\n\n"
    "不要把环境偶发问题、工具负面断言或一次性任务写成技能。\n"
    "若两个维度确实都无更新，回复「无需保存。」并结束，"
    "但不要轻易得出该结论。"
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
