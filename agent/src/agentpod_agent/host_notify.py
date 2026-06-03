"""Agent 容器 → 宿主：站内通知（fire-and-forget）。"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .config import get_settings
from .logging import get_logger
from .artifacts.store import get_category_name
from .workspace import get_workspace_id

log = get_logger("host_notify")


def _excerpt(content: str, max_len: int = 120) -> str:
    flat = re.sub(r"<[^>]+>", " ", content)
    flat = re.sub(r"[#*`>\-_[\]]", "", flat)
    flat = re.sub(r"\s+", " ", flat).strip()
    if len(flat) <= max_len:
        return flat
    return flat[: max_len - 1].rstrip() + "…"


def _artifact_link(category_id: str) -> str:
    return f"/artifacts/c/{category_id}"


async def notify_artifact_saved(art: dict[str, Any]) -> None:
    settings = get_settings()
    base = (settings.host_internal_url or "").rstrip("/")
    token = settings.internal_token
    user_id = settings.user_id
    if not base or not token or not user_id:
        return

    title = str(art.get("title") or "").strip()
    if not title:
        return

    category_id = str(art.get("category_id") or "").strip()
    if not category_id:
        return
    category_name = await get_category_name(category_id)
    label = category_name or "产物"
    body = _excerpt(str(art.get("content") or ""))
    payload = {
        "kind": "success",
        "category": f"保存产物（{label}）",
        "title": title,
        "body": body,
        "link": _artifact_link(category_id),
    }
    headers = {
        "X-Internal-Token": token,
        "X-User-Id": user_id,
        "X-Workspace-Id": get_workspace_id(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{base}/internal/notifications",
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 400:
                log.warning(
                    "artifact_notify_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
    except Exception as exc:
        log.warning("artifact_notify_error", error=str(exc))


async def notify_background_review(*, summary: str, session_id: str) -> None:
    settings = get_settings()
    base = (settings.host_internal_url or "").rstrip("/")
    token = settings.internal_token
    user_id = settings.user_id
    if not base or not token or not user_id:
        return

    text = (summary or "").strip()
    if not text:
        return

    payload = {
        "kind": "info",
        "category": "自我改进",
        "title": "后台已更新记忆或技能",
        "body": text[:500],
        "link": "/memory",
    }
    headers = {
        "X-Internal-Token": token,
        "X-User-Id": user_id,
        "X-Workspace-Id": get_workspace_id(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{base}/internal/notifications",
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 400:
                log.warning(
                    "background_review_notify_failed",
                    status=resp.status_code,
                    session_id=session_id,
                    body=resp.text[:200],
                )
    except Exception as exc:
        log.warning("background_review_notify_error", session_id=session_id, error=str(exc))
