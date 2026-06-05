"""用户请求是否应走 todo 拆解：LLM 语义分类。"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.llm_classifier import classify_json
from ..logging import get_logger

log = get_logger("todo_intent")

_TODO_INTENT_MARKER = "## Todo intent (this turn)"

_TODO_INTENT_SYSTEM_PROMPT = (
    "你是任务规划分类器。根据用户消息判断：agent 是否应先调用 todo 工具拆解步骤，再逐步执行。"
    "todo 由 agent 自行 confirm 节点，无需用户点击确认。\n\n"
    "needs_todo=true 典型情况：\n"
    "- 多步实施、开发、排查、迁移，需要按顺序推进\n"
    "- 多个交付物或子任务（如 API + 文档 + 测试）\n"
    "- 用户要求分步、拆解、或展示执行进度\n\n"
    "needs_todo=false 典型情况：\n"
    "- 单轮问答、解释、翻译、总结、概念对比\n"
    "- 单次读/搜/看/列信息\n"
    "- 单一小动作（改一行、查一个值、执行一条命令）\n\n"
    '输出严格 JSON：{"needs_todo": true|false, "reason": "一句中文说明"}'
)


@dataclass(frozen=True, slots=True)
class TodoIntent:
    needs_todo: bool
    reason: str = ""


async def assess_todo_intent(
    user_text: str,
    *,
    session_id: str | None = None,
) -> TodoIntent:
    text = str(user_text or "").strip()
    if not text:
        return TodoIntent(needs_todo=False)

    try:
        parsed = await classify_json(
            system_prompt=_TODO_INTENT_SYSTEM_PROMPT,
            user_content=text,
            scenario="todo_intent",
            session_id=session_id,
            retry_log_event="todo_intent_disable_thinking_retry",
        )
        intent = TodoIntent(
            needs_todo=bool(parsed.get("needs_todo", False)),
            reason=str(parsed.get("reason") or "").strip(),
        )
        log.info(
            "todo_intent_assessed",
            needs_todo=intent.needs_todo,
            reason=intent.reason[:120],
            session_id=session_id,
        )
        return intent
    except Exception as exc:
        log.warning("todo_intent_assess_failed", error=str(exc), session_id=session_id)
        return TodoIntent(needs_todo=False, reason="classifier unavailable")


def messages_require_todo_intent(messages: list[dict[str, object]]) -> bool:
    for msg in messages:
        if msg.get("role") != "system":
            continue
        content = str(msg.get("content") or "")
        if content.startswith(_TODO_INTENT_MARKER):
            return True
    return False


def build_todo_intent_system_message(intent: TodoIntent) -> str:
    if not intent.needs_todo:
        return ""
    reason = intent.reason or "multi_step"
    return (
        f"{_TODO_INTENT_MARKER}\n"
        f"Assessment: multi-step work likely ({reason}). "
        "Before any mutating tool (write_file, patch, terminal, execute_code, memory/skill/artifact writes), "
        "call todo(action=create) with 2–20 ordered steps, then todo(action=confirm) for each step as you execute. "
        "Do not skip todo for this turn unless the request collapses to a single trivial action after inspection."
    )
