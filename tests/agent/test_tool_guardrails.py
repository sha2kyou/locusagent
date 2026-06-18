"""工具循环护栏单元测试。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from locus_agent.core.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailController,
    classify_tool_failure,
    guardrail_config_from_settings,
)


def test_classify_tool_failure_error_prefix() -> None:
    assert classify_tool_failure("read_file", "Error: not found") is True
    assert classify_tool_failure("read_file", "ok") is False


def test_classify_tool_failure_avoids_substring_false_positive() -> None:
    assert classify_tool_failure("read_file", '{"items": [], "note": "no failure"}') is False
    assert classify_tool_failure("read_file", '{"error": null, "items": []}') is False


def test_classify_tool_failure_json_error_field() -> None:
    assert classify_tool_failure("read_file", '{"error": "disk full"}') is True
    assert classify_tool_failure("terminal", '{"exit_code": 1, "stdout": ""}') is True


def test_exact_failure_blocks_repeat_call() -> None:
    cfg = ToolCallGuardrailConfig(
        warnings_enabled=True,
        hard_stop_enabled=True,
        exact_failure_block_after=2,
    )
    ctrl = ToolCallGuardrailController(cfg)
    args = {"path": "foo.txt"}

    ctrl.after_call("read_file", args, "Error: missing", failed=True)
    pre = ctrl.before_call("read_file", args)
    assert pre.action == "allow"

    ctrl.after_call("read_file", args, "Error: missing", failed=True)
    pre = ctrl.before_call("read_file", args)
    assert pre.action == "block"
    assert not pre.allows_execution
    assert not pre.should_stop_turn
    assert ctrl.turn_stop_decision is None


def test_idempotent_no_progress_warning() -> None:
    cfg = ToolCallGuardrailConfig(
        hard_stop_enabled=False,
        no_progress_warn_after=2,
    )
    ctrl = ToolCallGuardrailController(cfg)
    args = {"path": "foo.txt"}

    d1 = ctrl.after_call("read_file", args, "same body", failed=False)
    assert d1.action == "allow"
    d2 = ctrl.after_call("read_file", args, "same body", failed=False)
    assert d2.action == "warn"
    assert d2.code == "idempotent_no_progress_warning"


def test_memory_recall_is_idempotent() -> None:
    cfg = ToolCallGuardrailConfig(hard_stop_enabled=False, no_progress_warn_after=2)
    ctrl = ToolCallGuardrailController(cfg)
    args = {"action": "recall", "query": "foo"}

    ctrl.after_call("memory", args, '{"items":[]}', failed=False)
    d2 = ctrl.after_call("memory", args, '{"items":[]}', failed=False)
    assert d2.action == "warn"


def test_memory_add_not_idempotent_no_progress() -> None:
    cfg = ToolCallGuardrailConfig(hard_stop_enabled=False, no_progress_warn_after=2)
    ctrl = ToolCallGuardrailController(cfg)
    args = {"action": "add", "content": "x"}

    ctrl.after_call("memory", args, "memory#1 saved", failed=False)
    d2 = ctrl.after_call("memory", args, "memory#2 saved", failed=False)
    assert d2.action == "allow"


def test_same_tool_failure_halt() -> None:
    cfg = ToolCallGuardrailConfig(
        hard_stop_enabled=True,
        same_tool_failure_halt_after=3,
    )
    ctrl = ToolCallGuardrailController(cfg)
    for i in range(3):
        ctrl.after_call("terminal", {"cmd": f"ls {i}"}, "Error: fail", failed=True)
    d = ctrl.after_call("terminal", {"cmd": "ls 3"}, "Error: fail", failed=True)
    assert d.action == "halt"
    assert ctrl.turn_stop_decision is not None
    assert ctrl.turn_stop_decision.should_stop_turn


def test_parallel_after_call_counts_under_lock() -> None:
    cfg = ToolCallGuardrailConfig(
        hard_stop_enabled=True,
        same_tool_failure_halt_after=4,
    )
    ctrl = ToolCallGuardrailController(cfg)
    args = {"path": "same.txt"}

    def _fail_once() -> None:
        ctrl.after_call("read_file", args, "Error: x", failed=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: _fail_once(), range(4)))

    assert ctrl.turn_stop_decision is not None
    assert ctrl.turn_stop_decision.action == "halt"
    assert ctrl.turn_stop_decision.count >= 4


def test_hard_stop_disabled_no_block() -> None:
    cfg = ToolCallGuardrailConfig(
        hard_stop_enabled=False,
        exact_failure_block_after=1,
    )
    ctrl = ToolCallGuardrailController(cfg)
    args = {"path": "x"}
    ctrl.after_call("read_file", args, "Error: a", failed=True)
    ctrl.after_call("read_file", args, "Error: b", failed=True)
    pre = ctrl.before_call("read_file", args)
    assert pre.action == "allow"
    assert ctrl.turn_stop_decision is None


def test_guardrail_config_caps_warn_above_block() -> None:

    class _S:
        tool_guardrail_warnings_enabled = True
        tool_guardrail_hard_stop_enabled = True
        tool_guardrail_exact_failure_warn_after = 10
        tool_guardrail_exact_failure_block_after = 3
        tool_guardrail_same_tool_failure_warn_after = 9
        tool_guardrail_same_tool_failure_halt_after = 2
        tool_guardrail_no_progress_warn_after = 8
        tool_guardrail_no_progress_block_after = 4

    cfg = guardrail_config_from_settings(_S())
    assert cfg.exact_failure_warn_after == 3
    assert cfg.exact_failure_block_after == 3
    assert cfg.same_tool_failure_warn_after == 2
    assert cfg.same_tool_failure_halt_after == 2
    assert cfg.no_progress_warn_after == 4
    assert cfg.no_progress_block_after == 4


def test_guardrail_block_content_parsed_as_failure() -> None:
    payload = json.dumps({"error": "blocked", "guardrail": "repeated_exact_failure_block", "count": 5})
    assert classify_tool_failure("read_file", payload) is True
