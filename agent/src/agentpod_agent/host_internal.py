"""Agent → Host internal API 公共鉴权头。"""

from __future__ import annotations

import httpx

from .config import get_settings
from .logging import get_logger

log = get_logger("host_internal")


class HostInternalError(RuntimeError):
    pass


def internal_base_and_headers(*, workspace_id: str | None = None) -> tuple[str, dict[str, str]]:
    settings = get_settings()
    base = (settings.host_internal_url or "").rstrip("/")
    token = settings.internal_token
    user_id = settings.user_id
    if not base or not token or not user_id:
        raise HostInternalError("host internal auth not configured")
    headers = {"X-Internal-Token": token, "X-User-Id": user_id}
    if workspace_id:
        headers["X-Workspace-Id"] = workspace_id
    return base, headers


def error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "").strip() or f"http {resp.status_code}"
    detail = data.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return str(data)
