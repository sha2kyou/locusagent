"""Agent 内部 API 仅允许来自私有网络（Docker/本机），公网经 Caddy 亦应被挡。"""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..internal_paths import is_agent_internal_path


def _parse_allowed_networks(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return nets


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return None
    return request.client.host


def _ip_allowed(
    ip_str: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]
) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def install_internal_network_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def _guard(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path
        if not is_agent_internal_path(path):
            return await call_next(request)

        settings = get_settings()
        if not settings.internal_network_guard_enabled:
            return await call_next(request)

        networks = _parse_allowed_networks(settings.internal_allowed_cidrs)
        if not networks:
            return JSONResponse(
                {"error": {"code": "internal_network_misconfigured"}},
                status_code=503,
            )

        client_ip = _client_ip(request)
        if client_ip is None or not _ip_allowed(client_ip, networks):
            return JSONResponse(
                {"error": {"code": "internal_network_forbidden"}},
                status_code=403,
            )
        return await call_next(request)
