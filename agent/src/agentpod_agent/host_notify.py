"""Agent 容器 → 宿主：站内通知（fire-and-forget）。"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .config import get_settings
from .logging import get_logger
from .artifacts.store import get_category_name

log = get_logger("host_notify")


def _excerpt(content: str, max_len: int = 120) -> str:
    flat = re.sub(r"<[^>]+>", " ", content)
    flat = re.sub(r"[#*`>\-_[\]]", "", flat)
    flat = re.sub(r"\s+", " ", flat).strip()
    if len(flat) <= max_len:
        return flat
    return flat[: max_len - 1].rstrip() + "…"


def _artifact_link(category_id: str | None) -> str:
    if category_id:
        return f"/artifacts/c/{category_id}"
    return "/artifacts"


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

    category_id = art.get("category_id")
    category_name = await get_category_name(str(category_id) if category_id else None)
    label = category_name or "未分类"
    body = _excerpt(str(art.get("content") or ""))
    payload = {
        "kind": "success",
        "category": f"保存产物（{label}）",
        "title": title,
        "body": body,
        "link": _artifact_link(str(category_id) if category_id else None),
    }
    headers = {
        "X-Internal-Token": token,
        "X-User-Id": user_id,
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
