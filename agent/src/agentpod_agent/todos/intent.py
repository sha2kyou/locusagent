"""用户请求是否应走 todo 拆解：LLM 语义分类。"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.llm_classifier import classify_json
from ..logging import get_logger

log = get_logger("todo_intent")

_TODO_INTENT_MARKER = "## 本回合任务拆解意图"

# 与 tools/todo.py description 共享：何时应/不应拆解
TODO_WHEN_TO_USE = (
    "在以下情况应调用 todo 拆解任务（action 取 create）：\n"
    "- 多步实施、开发、排查、迁移，需要按顺序推进\n"
    "- 多个交付物或子任务（如接口、文档与测试）\n"
    "- 用户要求分步执行或展示进度"
)

TODO_WHEN_TO_SKIP = (
    "以下情况可跳过 todo：\n"
    "- 单轮问答、解释、翻译、总结、概念对比\n"
    "- 单次读、搜、看、列信息\n"
    "- 单一小动作（改一行、查一个值、执行一条命令）"
)

TODO_TOOL_USAGE_GUIDANCE = f"{TODO_WHEN_TO_USE}\n\n{TODO_WHEN_TO_SKIP}"

_TODO_INTENT_SYSTEM_PROMPT = (
    "你是任务规划分类器。根据用户消息判断：助手是否应先调用 todo 拆解步骤，再逐步执行。"
    "todo 由助手自行确认节点，无需用户点击确认。\n\n"
    f"{TODO_WHEN_TO_USE}\n\n"
    f"{TODO_WHEN_TO_SKIP}\n\n"
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
        return TodoIntent(needs_todo=False, reason="分类器不可用")


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
    reason = intent.reason or "多步任务"
    return (
        f"{_TODO_INTENT_MARKER}\n"
        f"评估：疑似多步任务（{reason}）。"
        "在调用任何会修改状态的工具之前，"
        "先调用 todo 拆解二至二十个有序步骤（action 取 create），"
        "执行过程中用 todo 确认节点（action 取 confirm）。"
        "除非检查后发现请求已退化为单一琐碎操作，否则本回合不可跳过 todo。"
    )
