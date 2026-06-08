"""无登录页：首次请求自动签发 session cookie。"""

from __future__ import annotations

from fastapi import Request

from ..bootstrap import ensure_host_ready
from .session import read_session

STATE_ISSUE_SESSION = "issue_session"


async def bootstrap_session(request: Request) -> bool:
    if read_session(request):
        return True
    if getattr(request.state, STATE_ISSUE_SESSION, False):
        return True
    await ensure_host_ready()
    request.state.issue_session = True
    return True


def should_issue_session(request: Request) -> bool:
    return bool(getattr(request.state, STATE_ISSUE_SESSION, False))
