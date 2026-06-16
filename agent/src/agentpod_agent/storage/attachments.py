"""Object storage helpers for large binary payloads."""

from __future__ import annotations

import re
from pathlib import PurePath

import httpx

from ..config import get_settings
from ..host_internal import error_detail, internal_base_and_headers
from ..workspace import get_workspace_id
from ..logging import get_logger

log = get_logger("attachment_storage")

TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=60.0, pool=5.0)

_ATTACHMENT_ID_RE = re.compile(r"^att_[\w-]+$")
_FILE_EXT_RE = re.compile(r"^\.[A-Za-z0-9._-]+$")


class AttachmentStorageError(RuntimeError):
    pass


def _require_attachment_storage() -> None:
    if get_settings().attachment_storage != "local":
        raise AttachmentStorageError("attachment storage is not enabled")


def blob_object_key(content_sha256: str) -> str:
    digest = content_sha256.strip().lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise AttachmentStorageError("invalid content sha256 for blob key")
    return f"{get_workspace_id()}/blobs/{digest}"


def file_object_key(attachment_id: str, filename: str) -> str:
    """用户上传原文件：{workspace}/files/{att_xxx}{原后缀}。"""
    aid = str(attachment_id or "").strip()
    if not _ATTACHMENT_ID_RE.fullmatch(aid):
        raise AttachmentStorageError("invalid attachment id for file key")
    ext = PurePath(str(filename or "")).suffix
    if ext and not _FILE_EXT_RE.fullmatch(ext):
        ext = ""
    return f"{get_workspace_id()}/files/{aid}{ext}"


def legacy_blob_object_key(content_sha256: str) -> str:
    """旧版 key 带 attachments/ 前缀（与 data_dir/attachments 根目录重复）。"""
    return f"attachments/{blob_object_key(content_sha256)}"


def upload_was_skipped(uploaded: dict[str, str | bool]) -> bool:
    skipped = uploaded.get("skipped", False)
    return skipped is True or skipped == "true"


async def _ensure_bucket() -> None:
    _require_attachment_storage()
    base, headers = internal_base_and_headers()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{base}/internal/attachments/ensure-bucket", headers=headers)
    if resp.status_code >= 400:
        raise AttachmentStorageError(error_detail(resp))


async def _fetch_object(object_key: str) -> bytes | None:
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


async def resolve_attachment_bytes(
    object_key: str,
    *,
    content_sha256: str | None = None,
) -> tuple[bytes | None, str | None]:
    """按 object_key → canonical blob 顺序解析，返回 (data, 实际命中的 key)。"""
    key = str(object_key or "").strip()
    if key:
        data = await _fetch_object(key)
        if data is not None:
            return data, key
    if "/files/" in key:
        return None, None
    digest = str(content_sha256 or "").strip().lower()
    if not digest:
        return None, None
    canonical = blob_object_key(digest)
    if canonical != key:
        data = await _fetch_object(canonical)
        if data is not None:
            return data, canonical
    legacy = legacy_blob_object_key(digest)
    if legacy != key:
        data = await _fetch_object(legacy)
        if data is not None:
            return data, legacy
    return None, None


async def load_attachment_bytes(
    object_key: str,
    *,
    content_sha256: str | None = None,
) -> bytes | None:
    data, _ = await resolve_attachment_bytes(object_key, content_sha256=content_sha256)
    return data


async def _put_object(*, object_key: str, mime_type: str, data: bytes) -> dict[str, str | bool]:
    await _ensure_bucket()
    base, headers = internal_base_and_headers(workspace_id=get_workspace_id())
    headers["X-Object-Key"] = object_key
    headers["Content-Type"] = mime_type
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.put(f"{base}/internal/attachments/objects", headers=headers, content=data)
    if resp.status_code >= 400:
        raise AttachmentStorageError(error_detail(resp))
    body = resp.json()
    if not isinstance(body, dict):
        raise AttachmentStorageError("invalid host response")
    return {
        "object_key": str(body.get("object_key") or object_key),
        "etag": str(body.get("etag") or ""),
        "skipped": bool(body.get("skipped")),
    }


async def save_attachment_bytes(
    *,
    content_sha256: str,
    mime_type: str,
    data: bytes,
) -> dict[str, str | bool]:
    key = blob_object_key(content_sha256)
    return await _put_object(object_key=key, mime_type=mime_type, data=data)


async def save_attachment_file(
    *,
    object_key: str,
    mime_type: str,
    data: bytes,
) -> dict[str, str | bool]:
    return await _put_object(object_key=object_key, mime_type=mime_type, data=data)


async def delete_attachment_objects(object_keys: list[str]) -> None:
    keys = [k for k in object_keys if k]
    if not keys:
        return
    _require_attachment_storage()
    base, headers = internal_base_and_headers(workspace_id=get_workspace_id())
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{base}/internal/attachments/delete",
            headers=headers,
            json={"keys": keys},
        )
    if resp.status_code >= 400:
        log.warning("attachment_delete_failed", error=error_detail(resp))
