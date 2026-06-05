"""当前 chat run 上下文（tool 内可读 session_id）。"""

from __future__ import annotations

from contextvars import ContextVar, Token

_chat_session_id: ContextVar[str | None] = ContextVar("chat_session_id", default=None)
_todo_intent_required: ContextVar[bool] = ContextVar("todo_intent_required", default=False)


def set_chat_session_id(session_id: str | None) -> Token:
    return _chat_session_id.set(str(session_id).strip() or None)


def reset_chat_session_id(token: Token) -> None:
    _chat_session_id.reset(token)


def get_chat_session_id() -> str | None:
    return _chat_session_id.get()


def set_todo_intent_required(required: bool) -> Token:
    return _todo_intent_required.set(bool(required))


def reset_todo_intent_required(token: Token) -> None:
    _todo_intent_required.reset(token)


def get_todo_intent_required() -> bool:
    return _todo_intent_required.get()
