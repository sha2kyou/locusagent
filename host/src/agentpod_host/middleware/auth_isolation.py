"""鉴权类型隔离：Session 路径白名单。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..auth.session import SESSION_COOKIE_NAME
from ..internal_paths import is_agent_internal_path, is_internal_session_path

SESSION_ONLY_PREFIXES = (
    "/api/workspace/",
    "/api/workspaces/",
    "/api/me",
    "/api/settings/",
    "/api/notifications/",
    "/api/scheduled-tasks",
)

PUBLIC_PATHS = {
    "/health",
}

PUBLIC_PREFIXES = (
    "/api/oauth/",
    "/api/auth/",
)


def install_auth_isolation(app: FastAPI) -> None:
    @app.middleware("http")
    async def _auth_isolation(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path

        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")

        if any(path.startswith(p) for p in SESSION_ONLY_PREFIXES) or is_internal_session_path(path):
            if has_bearer:
                return JSONResponse(
                    {"error": {"code": "bearer_on_session_path"}},
                    status_code=403,
                )
            return await call_next(request)

        if is_agent_internal_path(path):
            return await call_next(request)

        if has_bearer:
            return JSONResponse(
                {"error": {"code": "bearer_not_supported"}},
                status_code=403,
            )

        return await call_next(request)
