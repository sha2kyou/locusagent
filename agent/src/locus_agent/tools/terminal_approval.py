"""终端命令用户确认（参考 Hermes approval.py 的阻塞等待与持久白名单模式）。

不在白名单且不在黑名单的可执行名，执行前须用户确认：
once / always（写入白名单）/ deny / always_deny（写入黑名单）。
超时默认 deny。非交互上下文（无 SSE emitter）立即拒绝，不阻塞等待。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from locus_shared.settings_store import (
    append_terminal_denylist_command,
    append_terminal_whitelist_command,
    reload_runtime_config,
)

from ..config import get_settings
from ..core.run_context import get_chat_run_id, get_chat_session_id, get_run_event_emitter
from ..logging import get_logger

log = get_logger("terminal_approval")

ApprovalChoice = Literal["once", "always", "deny", "always_deny"]
TERMINAL_APPROVAL_TIMEOUT_S = 30.0

_pending_lock = asyncio.Lock()
_pending: dict[str, "_PendingApproval"] = {}


@dataclass
class _PendingApproval:
    approval_id: str
    session_id: str
    run_id: str
    tool_call_id: str
    command: str
    head: str
    expires_at: float
    event: asyncio.Event = field(default_factory=asyncio.Event)
    choice: ApprovalChoice | None = None
    resolved: bool = False


def command_set(raw: str) -> set[str]:
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def classify_terminal_head(head: str) -> Literal["allow", "deny", "confirm"]:
    """白名单自动执行；黑名单自动拒绝；其余须确认。"""
    settings = get_settings()
    head = head.strip().lower()
    if head in command_set(settings.terminal_denylist):
        return "deny"
    if head in command_set(settings.terminal_whitelist):
        return "allow"
    return "confirm"


def _pending_to_public(item: _PendingApproval) -> dict[str, Any]:
    return {
        "approval_id": item.approval_id,
        "command": item.command,
        "head": item.head,
        "tool_call_id": item.tool_call_id,
        "run_id": item.run_id,
        "timeout_seconds": int(TERMINAL_APPROVAL_TIMEOUT_S),
        "expires_at": item.expires_at,
    }


async def request_terminal_command_approval(
    *,
    command: str,
    head: str,
    tool_call_id: str = "",
) -> None:
    """阻塞直至用户选择或超时；deny / always_deny / 超时抛 ToolError。"""
    from .base import ToolError

    emitter = get_run_event_emitter()
    if emitter is None:
        raise ToolError(
            f"command '{head.strip().lower()}' requires user approval; "
            "not available in non-interactive runs (scheduled tasks / sync API)"
        )

    session_id = get_chat_session_id() or ""
    run_id = get_chat_run_id() or ""
    approval_id = f"tappr_{uuid.uuid4().hex[:16]}"
    pending = _PendingApproval(
        approval_id=approval_id,
        session_id=session_id,
        run_id=run_id,
        tool_call_id=tool_call_id,
        command=command,
        head=head.strip().lower(),
        expires_at=time.time() + TERMINAL_APPROVAL_TIMEOUT_S,
    )
    async with _pending_lock:
        _pending[approval_id] = pending

    try:
        await _emit_approval_request(pending, emitter)
        choice = await _wait_for_choice(pending, timeout_s=TERMINAL_APPROVAL_TIMEOUT_S)
        if choice == "once":
            return
        if choice == "always":
            append_terminal_whitelist_command(pending.head)
            reload_runtime_config()
            log.info("terminal_whitelist_added", head=pending.head)
            return
        if choice == "always_deny":
            append_terminal_denylist_command(pending.head)
            reload_runtime_config()
            log.info("terminal_denylist_added", head=pending.head)
            raise ToolError(f"command '{pending.head}' permanently denied by user")
        raise ToolError(f"command '{pending.head}' denied by user")
    finally:
        async with _pending_lock:
            _pending.pop(approval_id, None)


async def resolve_terminal_approval(
    approval_id: str,
    *,
    choice: ApprovalChoice,
    session_id: str,
) -> dict[str, Any]:
    async with _pending_lock:
        pending = _pending.get(approval_id)
        if pending is None:
            return {"ok": False, "error": "approval_not_found"}
        if pending.session_id != session_id:
            return {"ok": False, "error": "session_mismatch"}
        if pending.resolved:
            return {"ok": True, "choice": pending.choice, "already_resolved": True}
        if choice not in {"once", "always", "deny", "always_deny"}:
            return {"ok": False, "error": "invalid_choice"}
        pending.choice = choice
        pending.resolved = True
    pending.event.set()
    return {"ok": True, "choice": choice}


async def list_pending_terminal_approvals(session_id: str) -> list[dict[str, Any]]:
    async with _pending_lock:
        return [
            _pending_to_public(item)
            for item in _pending.values()
            if item.session_id == session_id and not item.resolved
        ]


async def deny_pending_for_session(session_id: str) -> int:
    """取消 run 时拒绝该会话所有待确认命令。"""
    to_signal: list[_PendingApproval] = []
    async with _pending_lock:
        for item in _pending.values():
            if item.session_id != session_id or item.resolved:
                continue
            item.choice = "deny"
            item.resolved = True
            to_signal.append(item)
    for item in to_signal:
        item.event.set()
    return len(to_signal)


async def _emit_approval_request(
    pending: _PendingApproval,
    emitter: Any,
) -> None:
    await emitter(
        {
            "type": "terminal_approval",
            "ephemeral": True,
            "approval_id": pending.approval_id,
            "command": pending.command,
            "head": pending.head,
            "tool_call_id": pending.tool_call_id,
            "timeout_seconds": int(TERMINAL_APPROVAL_TIMEOUT_S),
            "expires_at": pending.expires_at,
        }
    )


async def _wait_for_choice(pending: _PendingApproval, *, timeout_s: float) -> ApprovalChoice:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while True:
        if pending.resolved and pending.choice is not None:
            return pending.choice
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            async with _pending_lock:
                if not pending.resolved:
                    pending.choice = "deny"
                    pending.resolved = True
            log.info("terminal_approval_timeout", approval_id=pending.approval_id, head=pending.head)
            return "deny"
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=min(1.0, remaining))
        except TimeoutError:
            continue
