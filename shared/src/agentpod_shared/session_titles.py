"""Default session titles aligned with frontend i18n (chat.session.defaultTitle)."""

from __future__ import annotations

DEFAULT_SESSION_TITLE_ZH = "新对话"
DEFAULT_SESSION_TITLE_EN = "New chat"

DEFAULT_SESSION_TITLES = frozenset({DEFAULT_SESSION_TITLE_ZH, DEFAULT_SESSION_TITLE_EN})


def default_session_title(locale: str | None) -> str:
    loc = (locale or "en").strip().lower()
    if loc == "zh":
        return DEFAULT_SESSION_TITLE_ZH
    return DEFAULT_SESSION_TITLE_EN


def is_default_session_title(title: str | None) -> bool:
    t = (title or "").strip()
    return not t or t in DEFAULT_SESSION_TITLES


def display_session_title(stored: str | None, *, locale: str | None) -> str:
    """Stored title for DB/tool output; empty uses locale default."""
    t = (stored or "").strip()
    if t:
        return t
    return default_session_title(locale)
