"""Workspace API 统一错误结构：{"error": {"code", "message", "detail?"}}."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class WsError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        detail: Any = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def ws_error_body(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return body


def ws_json_error(
    code: str,
    message: str,
    status_code: int = 400,
    detail: Any = None,
) -> JSONResponse:
    return JSONResponse(ws_error_body(code, message, detail), status_code=status_code)


def _is_workspace_path(request: Request) -> bool:
    return request.url.path.startswith("/workspace")


async def ws_error_handler(_request: Request, exc: WsError) -> JSONResponse:
    return ws_json_error(exc.code, exc.message, exc.status_code, exc.detail)


async def ws_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    if not _is_workspace_path(request):
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)
    return ws_json_error(
        "validation_error",
        "request validation failed",
        status_code=422,
        detail=exc.errors(),
    )
