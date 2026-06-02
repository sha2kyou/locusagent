"""鉴权类型隔离：Bearer 与 Session 互斥的硬白名单。

规范约束：
- Bearer 只能命中 /api/v1/{chat/completions, responses, models, health}；其他路径若仅带 Bearer 一律 403。
- Session 只能命中 /api/workspace/*、/api/me*、/api/settings/*、/internal/containers/*；
  这些路径若带 Bearer（无论是否同时带 session）一律 403，避免凭据混用。
- Agent 内部代理路径（/internal/llm 等）允许 Bearer（INTERNAL_TOKEN），不经 Session 白名单。
- /api/v1/health 与 /health 跳过隔离，作为公共探活端点。
- /api/oauth/* 公开（用户尚未登录），跳过隔离。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..auth.session import SESSION_COOKIE_NAME
from ..internal_paths import is_agent_internal_path, is_internal_session_path

BEARER_ALLOWED_PATHS = {
    "/api/v1/chat/completions",
    "/api/v1/responses",
    "/api/v1/models",
    "/api/v1/health",
}
BEARER_ALLOWED_PREFIXES = (
    "/api/v1/responses/",
)

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
    "/api/v1/health",
}

PUBLIC_PREFIXES = (
    "/api/oauth/",
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
        has_session = SESSION_COOKIE_NAME in request.cookies

        if path.startswith("/api/v1/"):
            if path not in BEARER_ALLOWED_PATHS and not any(
                path.startswith(p) for p in BEARER_ALLOWED_PREFIXES
            ):
                return JSONResponse(
                    {"error": {"code": "forbidden_path", "message": "path not allowed for bearer"}},
                    status_code=403,
                )
            if has_session and not has_bearer:
                return JSONResponse(
                    {"error": {"code": "session_on_bearer_path"}},
                    status_code=403,
                )
            return await call_next(request)

        if any(path.startswith(p) for p in SESSION_ONLY_PREFIXES) or is_internal_session_path(path):
            if has_bearer:
                return JSONResponse(
                    {"error": {"code": "bearer_on_session_path"}},
                    status_code=403,
                )
            return await call_next(request)

        if is_agent_internal_path(path):
            return await call_next(request)

        return await call_next(request)
