"""当前 chat run 上下文（tool 内可读 session_id）。"""

from __future__ import annotations

from contextvars import ContextVar, Token

_chat_session_id: ContextVar[str | None] = ContextVar("chat_session_id", default=None)


def set_chat_session_id(session_id: str | None) -> Token:
    return _chat_session_id.set(str(session_id).strip() or None)


def reset_chat_session_id(token: Token) -> None:
    _chat_session_id.reset(token)


def get_chat_session_id() -> str | None:
    return _chat_session_id.get()
