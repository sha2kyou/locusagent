"""Attachment storage via Host proxy (no S3 credentials in container)."""

from __future__ import annotations

import hashlib

import httpx

from ..config import get_settings
from ..host_internal import HostInternalError, error_detail, internal_base_and_headers
from ..workspace import get_workspace_id
from ..logging import get_logger

log = get_logger("attachment_storage")

TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=60.0, pool=5.0)


class AttachmentStorageError(RuntimeError):
    pass


def _require_minio_proxy() -> None:
    if get_settings().attachment_storage != "minio":
        raise AttachmentStorageError("attachment storage is not minio")


def _object_key(*, attachment_id: str, kind: str, name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return f"attachments/{get_workspace_id()}/{attachment_id}/{kind}/{digest}"


async def _ensure_bucket() -> None:
    _require_minio_proxy()
    base, headers = internal_base_and_headers()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{base}/internal/attachments/ensure-bucket", headers=headers)
    if resp.status_code >= 400:
        raise AttachmentStorageError(error_detail(resp))


async def save_attachment_bytes(
    *,
    attachment_id: str,
    kind: str,
    name: str,
    mime_type: str,
    data: bytes,
) -> dict[str, str]:
    await _ensure_bucket()
    key = _object_key(attachment_id=attachment_id, kind=kind, name=name)
    base, headers = internal_base_and_headers(workspace_id=get_workspace_id())
    headers["X-Object-Key"] = key
    headers["Content-Type"] = mime_type
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.put(f"{base}/internal/attachments/objects", headers=headers, content=data)
    if resp.status_code >= 400:
        raise AttachmentStorageError(error_detail(resp))
    body = resp.json()
    if not isinstance(body, dict):
        raise AttachmentStorageError("invalid host response")
    return {
        "object_key": str(body.get("object_key") or key),
        "etag": str(body.get("etag") or ""),
    }


async def load_attachment_bytes(object_key: str) -> bytes | None:
    if not object_key:
        return None
    _require_minio_proxy()
    base, headers = internal_base_and_headers(workspace_id=get_workspace_id())
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{base}/internal/attachments/objects",
            headers=headers,
            params={"key": object_key},
        )
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise AttachmentStorageError(error_detail(resp))
    return resp.content


async def delete_attachment_objects(object_keys: list[str]) -> None:
    keys = [k for k in object_keys if k]
    if not keys:
        return
    _require_minio_proxy()
    base, headers = internal_base_and_headers(workspace_id=get_workspace_id())
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{base}/internal/attachments/delete",
            headers=headers,
            json={"keys": keys},
        )
    if resp.status_code >= 400:
        log.warning("attachment_delete_failed", error=error_detail(resp))
