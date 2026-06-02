"""单轮对话内的工具调用循环护栏（参考 Hermes tool_guardrails，无副作用控制器）。"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

IDEMPOTENT_TOOL_NAMES = frozenset(
    {
        "read_file",
        "search_files",
        "web_search",
        "web_extract",
        "session_search",
        "session_recall",
        "artifact_recall",
        "skill_view",
        "get_current_user",
        "notification_query",
        "scheduled_task_view",
        "env_vars",
        "summarize",
    }
)

MUTATING_TOOL_NAMES = frozenset(
    {
        "terminal",
        "execute_code",
        "write_file",
        "patch",
        "memory",
        "skill_manage",
        "artifact_save",
        "artifact_category_create",
        "manage_workspace",
        "scheduled_task_manage",
        "clarify",
    }
)

_MEMORY_READ_ACTIONS = frozenset({"read", "recall"})


@dataclass(frozen=True)
class ToolCallGuardrailConfig:
    warnings_enabled: bool = True
    hard_stop_enabled: bool = True
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5
    idempotent_tools: frozenset[str] = field(default_factory=lambda: IDEMPOTENT_TOOL_NAMES)
    mutating_tools: frozenset[str] = field(default_factory=lambda: MUTATING_TOOL_NAMES)


@dataclass(frozen=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, Any] | None) -> ToolCallSignature:
        canonical = canonical_tool_args(args or {})
        return cls(tool_name=tool_name, args_hash=_sha256(canonical))


@dataclass(frozen=True)
class ToolGuardrailDecision:
    action: str = "allow"  # allow | warn | block | halt
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}

    @property
    def should_stop_turn(self) -> bool:
        return self.action in {"block", "halt"}


class ToolCallGuardrailController:
    def __init__(self, config: ToolCallGuardrailConfig | None = None) -> None:
        self.config = config or ToolCallGuardrailConfig()
        self._lock = threading.Lock()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        with self._lock:
            self._exact_failure_counts: dict[ToolCallSignature, int] = {}
            self._same_tool_failure_counts: dict[str, int] = {}
            self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
            self._turn_stop_decision: ToolGuardrailDecision | None = None

    @property
    def turn_stop_decision(self) -> ToolGuardrailDecision | None:
        return self._turn_stop_decision

    @property
    def halt_decision(self) -> ToolGuardrailDecision | None:
        """兼容别名：block / halt 后应结束工具轮次。"""
        return self._turn_stop_decision

    def before_call(self, tool_name: str, args: Mapping[str, Any] | None) -> ToolGuardrailDecision:
        with self._lock:
            return self._before_call_unlocked(tool_name, args)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: bool | None = None,
    ) -> ToolGuardrailDecision:
        with self._lock:
            return self._after_call_unlocked(tool_name, args, result, failed=failed)

    def _before_call_unlocked(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
    ) -> ToolGuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)
        if not self.config.hard_stop_enabled:
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.config.exact_failure_block_after:
            decision = ToolGuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"已阻止 {tool_name}：相同参数已连续失败 {exact_count} 次。"
                    "请更换策略或说明阻塞原因，勿重复相同调用。"
                ),
                tool_name=tool_name,
                count=exact_count,
                signature=signature,
            )
            self._turn_stop_decision = decision
            return decision

        if self._is_idempotent(tool_name, args):
            record = self._no_progress.get(signature)
            if record is not None:
                _result_hash, repeat_count = record
                if repeat_count >= self.config.no_progress_block_after:
                    decision = ToolGuardrailDecision(
                        action="block",
                        code="idempotent_no_progress_block",
                        message=(
                            f"已阻止 {tool_name}：只读调用已连续返回相同结果 {repeat_count} 次。"
                            "请使用已有结果或更换查询。"
                        ),
                        tool_name=tool_name,
                        count=repeat_count,
                        signature=signature,
                    )
                    self._turn_stop_decision = decision
                    return decision

        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def _after_call_unlocked(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: bool | None = None,
    ) -> ToolGuardrailDecision:
        args = args if isinstance(args, Mapping) else {}
        signature = ToolCallSignature.from_call(tool_name, args)
        if failed is None:
            failed = classify_tool_failure(tool_name, result)

        if failed:
            exact_count = self._exact_failure_counts.get(signature, 0) + 1
            self._exact_failure_counts[signature] = exact_count
            self._no_progress.pop(signature, None)

            same_count = self._same_tool_failure_counts.get(tool_name, 0) + 1
            self._same_tool_failure_counts[tool_name] = same_count

            if self.config.hard_stop_enabled and same_count >= self.config.same_tool_failure_halt_after:
                decision = ToolGuardrailDecision(
                    action="halt",
                    code="same_tool_failure_halt",
                    message=(
                        f"已停止工具循环：{tool_name} 本轮已连续失败 {same_count} 次。"
                        "请改用其他工具或向用户说明阻塞。"
                    ),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )
                self._turn_stop_decision = decision
                return decision

            if self.config.warnings_enabled and exact_count >= self.config.exact_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="repeated_exact_failure_warning",
                    message=(
                        f"{tool_name} 在相同参数下已连续失败 {exact_count} 次，疑似死循环；"
                        "请先查看错误并调整参数或策略。"
                    ),
                    tool_name=tool_name,
                    count=exact_count,
                    signature=signature,
                )

            if self.config.warnings_enabled and same_count >= self.config.same_tool_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=(
                        f"{tool_name} 本轮已连续失败 {same_count} 次；"
                        "请诊断错误后换用其他工具或参数，勿重复同一路径。"
                    ),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )

            return ToolGuardrailDecision(tool_name=tool_name, count=exact_count, signature=signature)

        self._exact_failure_counts.pop(signature, None)
        self._same_tool_failure_counts.pop(tool_name, None)

        if not self._is_idempotent(tool_name, args):
            self._no_progress.pop(signature, None)
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        result_hash = _sha256(_canonical_result(result))
        previous = self._no_progress.get(signature)
        repeat_count = 1
        if previous is not None and previous[0] == result_hash:
            repeat_count = previous[1] + 1
        self._no_progress[signature] = (result_hash, repeat_count)

        if self.config.warnings_enabled and repeat_count >= self.config.no_progress_warn_after:
            return ToolGuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool_name} 已连续 {repeat_count} 次返回相同结果；"
                    "请直接使用已有信息或更换查询。"
                ),
                tool_name=tool_name,
                count=repeat_count,
                signature=signature,
            )

        return ToolGuardrailDecision(tool_name=tool_name, count=repeat_count, signature=signature)

    def _is_idempotent(self, tool_name: str, args: Mapping[str, Any] | None = None) -> bool:
        args = args if isinstance(args, Mapping) else {}
        if tool_name == "memory":
            return str(args.get("action", "")).lower() in _MEMORY_READ_ACTIONS
        if tool_name in self.config.mutating_tools:
            return False
        return tool_name in self.config.idempotent_tools


def canonical_tool_args(args: Mapping[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def classify_tool_failure(tool_name: str, result: str | None) -> bool:
    if not result:
        return False
    text = result.strip()
    if text.startswith("Error:") or text.startswith("error:"):
        return True
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("guardrail"):
        return True
    err = data.get("error")
    if err is not None and err is not False:
        if isinstance(err, str):
            return bool(err.strip())
        return True
    if data.get("ok") is False or data.get("success") is False:
        return True
    if tool_name == "terminal":
        exit_code = data.get("exit_code")
        if exit_code is not None and exit_code != 0:
            return True
    return False


def guardrail_block_content(decision: ToolGuardrailDecision) -> str:
    return json.dumps(
        {"error": decision.message, "guardrail": decision.code, "count": decision.count},
        ensure_ascii=False,
    )


def append_guardrail_guidance(result: str, decision: ToolGuardrailDecision) -> str:
    if decision.action not in {"warn", "halt"} or not decision.message:
        return result
    label = "工具循环熔断" if decision.action == "halt" else "工具循环警告"
    return f"{result or ''}\n\n[{label}: {decision.message}]"


def _cap_warn_block(warn_after: int, block_after: int) -> tuple[int, int]:
    warn = max(1, int(warn_after))
    block = max(1, int(block_after))
    if warn > block:
        warn = block
    return warn, block


def guardrail_config_from_settings(settings: Any) -> ToolCallGuardrailConfig:
    exact_warn, exact_block = _cap_warn_block(
        getattr(settings, "tool_guardrail_exact_failure_warn_after", 2),
        getattr(settings, "tool_guardrail_exact_failure_block_after", 5),
    )
    same_warn, same_halt = _cap_warn_block(
        getattr(settings, "tool_guardrail_same_tool_failure_warn_after", 3),
        getattr(settings, "tool_guardrail_same_tool_failure_halt_after", 8),
    )
    prog_warn, prog_block = _cap_warn_block(
        getattr(settings, "tool_guardrail_no_progress_warn_after", 2),
        getattr(settings, "tool_guardrail_no_progress_block_after", 5),
    )
    return ToolCallGuardrailConfig(
        warnings_enabled=bool(getattr(settings, "tool_guardrail_warnings_enabled", True)),
        hard_stop_enabled=bool(getattr(settings, "tool_guardrail_hard_stop_enabled", True)),
        exact_failure_warn_after=exact_warn,
        exact_failure_block_after=exact_block,
        same_tool_failure_warn_after=same_warn,
        same_tool_failure_halt_after=same_halt,
        no_progress_warn_after=prog_warn,
        no_progress_block_after=prog_block,
    )


def _canonical_result(result: str | None) -> str:
    if result is None:
        return ""
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return result
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
