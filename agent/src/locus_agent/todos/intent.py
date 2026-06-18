"""Whether a user request should use todo breakdown: LLM semantic classification."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.llm_classifier import classify_json
from ..logging import get_logger

log = get_logger("todo_intent")

_TODO_INTENT_MARKER = "## Turn task-breakdown intent"

# Shared with tools/todo.py description: when to break down vs skip
TODO_WHEN_TO_USE = (
    "Call todo to break down the task (action=create) when:\n"
    "- multi-step implementation, development, debugging, or migration that must proceed in order\n"
    "- multiple deliverables or subtasks (e.g. API, docs, and tests)\n"
    "- the user asks for step-by-step execution or progress visibility"
)

TODO_WHEN_TO_SKIP = (
    "You may skip todo when:\n"
    "- single-turn Q&A, explanation, translation, summary, or concept comparison\n"
    "- a single read, search, view, or list operation\n"
    "- one small action (change one line, look up one value, run one command)"
)

TODO_TOOL_USAGE_GUIDANCE = f"{TODO_WHEN_TO_USE}\n\n{TODO_WHEN_TO_SKIP}"

_TODO_INTENT_SYSTEM_PROMPT = (
    "You are a task-planning classifier. From the user message, decide whether the assistant should "
    "call todo to break down steps before executing. "
    "The assistant confirms steps itself; the user does not click to approve.\n\n"
    f"{TODO_WHEN_TO_USE}\n\n"
    f"{TODO_WHEN_TO_SKIP}\n\n"
    'Output strict JSON: {"needs_todo": true|false, "reason": "one-sentence explanation"}'
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
    reason = intent.reason or "multi-step task"
    return (
        f"{_TODO_INTENT_MARKER}\n"
        f"Assessment: likely multi-step task ({reason}). "
        "Before calling any state-mutating tool, "
        "call todo to break the work into two to twenty ordered steps (action=create); "
        "during execution confirm steps with todo (action=confirm). "
        "Do not skip todo this turn unless you verify the request collapsed to a single trivial action."
    )
