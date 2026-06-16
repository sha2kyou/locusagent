"""Memory term (long_term / short_term) resolution tests."""

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
        ("", MEMORY_ANCHOR_SHORT),
        (None, MEMORY_ANCHOR_SHORT),
    ],
)
def test_resolve_memory_anchor_input(raw: str | None, expected: str) -> None:
    assert resolve_memory_anchor_input(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["user", "memory", "identity", "experience", "长期", "短期", "foobar"],
)
def test_resolve_memory_anchor_input_rejects_non_term(raw: str) -> None:
    with pytest.raises(ValueError, match="long_term or short_term"):
        resolve_memory_anchor_input(raw)


@pytest.mark.parametrize(
    ("anchor", "label"),
    [
        ("identity", "long-term"),
        ("experience", "short-term"),
        (None, "short-term"),
    ],
)
def test_memory_term_label(anchor: str | None, label: str) -> None:
    assert memory_term_label(anchor) == label
