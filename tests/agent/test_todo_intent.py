"""todo 意图识别单元测试。"""

from __future__ import annotations

from locus_agent.todos.intent import (
    TodoIntent,
    build_todo_intent_system_message,
    messages_require_todo_intent,
)


def test_build_todo_intent_system_message_empty_when_not_needed() -> None:
    assert build_todo_intent_system_message(TodoIntent(needs_todo=False)) == ""


def test_build_todo_intent_system_message_when_needed() -> None:
    hint = build_todo_intent_system_message(TodoIntent(needs_todo=True, reason="多步开发"))
    assert hint.startswith("## Turn task-breakdown intent")
    assert "多步开发" in hint


def test_messages_require_todo_intent_from_system_message() -> None:
    hint = build_todo_intent_system_message(TodoIntent(needs_todo=True, reason="多步开发"))
    messages = [{"role": "system", "content": hint}, {"role": "user", "content": "go"}]
    assert messages_require_todo_intent(messages) is True
    assert messages_require_todo_intent([{"role": "user", "content": "hi"}]) is False
