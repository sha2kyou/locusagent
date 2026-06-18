"""session todo store 单元测试。"""

from __future__ import annotations

from locus_agent.todos.store import plan_is_active


def test_plan_is_active_with_pending_or_in_progress() -> None:
    assert plan_is_active([{"status": "pending"}, {"status": "done"}]) is True
    assert plan_is_active([{"status": "in_progress"}, {"status": "done"}]) is True


def test_plan_is_active_false_when_all_terminal() -> None:
    steps = [
        {"status": "done"},
        {"status": "skipped"},
        {"status": "interrupted"},
    ]
    assert plan_is_active(steps) is False


def test_plan_is_active_empty() -> None:
    assert plan_is_active([]) is False
    assert plan_is_active(None) is False
