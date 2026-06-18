"""工具参数解析单元测试。"""

from __future__ import annotations

from locus_agent.tools.args import pick_action, pick_int, pick_str


def test_pick_str_prefers_first_non_empty_key() -> None:
    assert pick_str({"content": "  hello  "}, "content", "text") == "hello"
    assert pick_str({"text": "fallback"}, "content", "text") == "fallback"
    assert pick_str({"content": "", "new_string": "x"}, "content", "new_string") == "x"
    assert pick_str({}, "content") == ""


def test_pick_int_accepts_aliases() -> None:
    assert pick_int({"id": 12}, "id", "memory_id") == 12
    assert pick_int({"memory_id": "7"}, "id", "memory_id") == 7
    assert pick_int({"id": ""}, "id") == 0


def test_pick_action_normalizes() -> None:
    assert pick_action({"action": " Remove "}) == "remove"
    assert pick_action({}) == ""
