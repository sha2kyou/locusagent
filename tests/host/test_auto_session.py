"""自动 session bootstrap。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from agentpod_host.auth.auto_session import bootstrap_session, should_issue_session
from agentpod_host.config import get_settings


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/me",
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_bootstrap_session_without_cookie():
    request = _request()

    with patch(
        "agentpod_host.auth.auto_session.ensure_host_ready",
        new=AsyncMock(),
    ):
        ok = await bootstrap_session(request)

    assert ok is True
    assert should_issue_session(request) is True
