"""共享 LLM JSON 分类器单元测试。"""

from __future__ import annotations

import pytest

from locus_agent.core.llm_classifier import parse_json_object


def test_parse_json_object_plain() -> None:
    parsed = parse_json_object('{"needs_todo": true, "reason": "多步开发"}')
    assert parsed["needs_todo"] is True
    assert parsed["reason"] == "多步开发"


def test_parse_json_object_fenced() -> None:
    raw = '```json\n{"should_review": false, "reason": "单轮问答"}\n```'
    parsed = parse_json_object(raw)
    assert parsed["should_review"] is False


def test_parse_json_object_invalid() -> None:
    with pytest.raises(ValueError):
        parse_json_object("not json")
