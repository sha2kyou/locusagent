"""响应阶段写入 session cookie。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request

from ..auth.session import issue_session
from ..auth.auto_session import should_issue_session


def install_auto_session(app: FastAPI) -> None:
    @app.middleware("http")
    async def _auto_session(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        response = await call_next(request)
        if should_issue_session(request):
            issue_session(response)
        return response
