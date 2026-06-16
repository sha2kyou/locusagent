"""Default session title helpers."""

from __future__ import annotations

import pytest

from agentpod_shared.session_titles import (
    DEFAULT_SESSION_TITLE_EN,
    DEFAULT_SESSION_TITLE_ZH,
    default_session_title,
    is_default_session_title,
)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("zh", DEFAULT_SESSION_TITLE_ZH),
        ("en", DEFAULT_SESSION_TITLE_EN),
        ("EN", DEFAULT_SESSION_TITLE_EN),
        (None, DEFAULT_SESSION_TITLE_EN),
    ],
)
def test_default_session_title(locale: str | None, expected: str) -> None:
    assert default_session_title(locale) == expected


@pytest.mark.parametrize(
    "title",
    ["", "  ", DEFAULT_SESSION_TITLE_ZH, DEFAULT_SESSION_TITLE_EN],
)
def test_is_default_session_title(title: str) -> None:
    assert is_default_session_title(title)


def test_is_default_session_title_custom() -> None:
    assert not is_default_session_title("My topic")
