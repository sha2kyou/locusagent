"""记忆 anchor / term 解析单元测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.memory import (
    MEMORY_ANCHOR_LONG,
    MEMORY_ANCHOR_SHORT,
    memory_term_label,
    resolve_memory_anchor_input,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("long_term", MEMORY_ANCHOR_LONG),
        ("short_term", MEMORY_ANCHOR_SHORT),
        ("user", MEMORY_ANCHOR_LONG),
        ("memory", MEMORY_ANCHOR_SHORT),
        ("identity", MEMORY_ANCHOR_LONG),
        ("experience", MEMORY_ANCHOR_SHORT),
        ("长期", MEMORY_ANCHOR_LONG),
        ("短期", MEMORY_ANCHOR_SHORT),
        ("", MEMORY_ANCHOR_SHORT),
        (None, MEMORY_ANCHOR_SHORT),
    ],
)
def test_resolve_memory_anchor_input(raw: str | None, expected: str) -> None:
    assert resolve_memory_anchor_input(raw) == expected


def test_resolve_memory_anchor_input_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="long_term or short_term"):
        resolve_memory_anchor_input("foobar")


@pytest.mark.parametrize(
    ("anchor", "label"),
    [
        ("identity", "长期"),
        ("experience", "短期"),
        ("user", "长期"),
        (None, "短期"),
    ],
)
def test_memory_term_label(anchor: str | None, label: str) -> None:
    assert memory_term_label(anchor) == label
