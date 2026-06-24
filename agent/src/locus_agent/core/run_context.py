"""当前 chat run 上下文（tool 内可读 session_id / run_id / 事件投递）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any

_chat_session_id: ContextVar[str | None] = ContextVar("chat_session_id", default=None)
_chat_run_id: ContextVar[str | None] = ContextVar("chat_run_id", default=None)
_run_event_emitter: ContextVar[Callable[[dict[str, Any]], Awaitable[None]] | None] = ContextVar(
    "run_event_emitter",
    default=None,
)


def set_chat_session_id(session_id: str | None) -> Token:
    return _chat_session_id.set(str(session_id).strip() or None)


def reset_chat_session_id(token: Token) -> None:
    _chat_session_id.reset(token)


def get_chat_session_id() -> str | None:
    return _chat_session_id.get()


def set_chat_run_id(run_id: str | None) -> Token:
    return _chat_run_id.set(str(run_id).strip() or None)


def reset_chat_run_id(token: Token) -> None:
    _chat_run_id.reset(token)


def get_chat_run_id() -> str | None:
    return _chat_run_id.get()


def set_run_event_emitter(
    emitter: Callable[[dict[str, Any]], Awaitable[None]] | None,
) -> Token:
    return _run_event_emitter.set(emitter)


def reset_run_event_emitter(token: Token) -> None:
    _run_event_emitter.reset(token)


def get_run_event_emitter() -> Callable[[dict[str, Any]], Awaitable[None]] | None:
    return _run_event_emitter.get()
