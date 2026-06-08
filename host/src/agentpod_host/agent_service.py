"""Sidecar 内 Agent 路由（单体同进程）。"""

from __future__ import annotations

from .config import Settings, get_settings


def agent_base_url(settings: Settings | None = None) -> str:
    return (settings or get_settings()).agent_service_url.rstrip("/")


def agent_url(path: str, settings: Settings | None = None) -> str:
    base = agent_base_url(settings)
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


async def load_internal_token() -> str | None:
    token = get_settings().agent_internal_token.strip()
    return token or None
