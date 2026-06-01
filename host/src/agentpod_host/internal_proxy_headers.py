"""内部代理转发上游时的请求头过滤。"""

from __future__ import annotations

from fastapi import Request

_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)

# 不得转发给外部 LLM / 第三方；Authorization 由代理单独注入。
_STRIP_TO_UPSTREAM = _HOP_HEADERS | frozenset(
    {
        "authorization",
        "cookie",
        "x-internal-token",
        "x-user-id",
        "x-workspace-id",
    }
)


def forward_headers_to_upstream(request: Request, *, authorization: str | None = None) -> dict[str, str]:
    out = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIP_TO_UPSTREAM
    }
    if authorization:
        out["Authorization"] = authorization
    return out
