"""todo 意图识别单元测试。"""

from __future__ import annotations

from agentpod_agent.todos.intent import (
    assess_todo_intent,
    build_todo_intent_system_message,
    messages_require_todo_intent,
)


def test_simple_qa_does_not_need_todo() -> None:
    intent = assess_todo_intent("什么是正态分布？")
    assert intent.needs_todo is False
    assert intent.score < 3


def test_feature_build_needs_todo() -> None:
    intent = assess_todo_intent("帮我开发一个用户登录模块，包含 API 和后端数据库")
    assert intent.needs_todo is True
    assert intent.score >= 3


def test_explicit_todo_needs_todo() -> None:
    intent = assess_todo_intent("把这个需求拆成 todo 并逐步执行")
    assert intent.needs_todo is True


def test_numbered_items_needs_todo() -> None:
    text = "1. 设计 API\n2. 实现后端\n3. 写测试"
    intent = assess_todo_intent(text)
    assert intent.needs_todo is True


def test_build_todo_intent_system_message_empty_when_not_needed() -> None:
    intent = assess_todo_intent("你好")
    assert build_todo_intent_system_message(intent) == ""


def test_messages_require_todo_intent_from_system_message() -> None:
    intent = assess_todo_intent("实现登录功能、注册功能和权限模块")
    hint = build_todo_intent_system_message(intent)
    assert hint
    messages = [{"role": "system", "content": hint}, {"role": "user", "content": "go"}]
    assert messages_require_todo_intent(messages) is True
    assert messages_require_todo_intent([{"role": "user", "content": "hi"}]) is False
