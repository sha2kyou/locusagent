"""Agent → Host：站内通知（fire-and-forget）。"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .artifacts.store import get_category_name
from .host_internal import HostInternalError, internal_base_and_headers
from .logging import get_logger

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


def _artifact_notify_category(label: str) -> str:
    prefix = "保存产物（"
    suffix = "）"
    max_label_len = max(1, 64 - len(prefix) - len(suffix))
    clean = (label or "产物").strip() or "产物"
    if len(clean) > max_label_len:
        clean = f"{clean[: max_label_len - 1].rstrip()}…"
    return f"{prefix}{clean}{suffix}"


def _notify_workspace_id() -> str | None:
    from locus_shared.workspace_ids import is_valid_workspace_id

    from .workspace import get_workspace_id

    wid = get_workspace_id().strip().lower()
    return wid if is_valid_workspace_id(wid) else None


async def notify_artifact_saved(art: dict[str, Any]) -> None:
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
        "category": _artifact_notify_category(label),
        "title": title[:200],
        "body": body[:4000],
        "link": _artifact_link(category_id),
    }
    try:
        base, headers = internal_base_and_headers(workspace_id=_notify_workspace_id())
    except HostInternalError as exc:
        log.warning("artifact_notify_skipped", reason=str(exc))
        return
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
    text = (summary or "").strip()
    if not text:
        return

    payload = {
        "kind": "success",
        "category": "自我改进",
        "title": "后台已更新记忆或技能",
        "body": text[:500],
        "link": "/memory",
    }
    try:
        base, headers = internal_base_and_headers(workspace_id=_notify_workspace_id())
    except HostInternalError as exc:
        log.warning("background_review_notify_skipped", session_id=session_id, reason=str(exc))
        return
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
