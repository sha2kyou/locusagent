"""附件对象存储代理：S3 凭据仅留在 Host。"""

from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from sqlalchemy import select

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..db import Workspace, get_session
from ..internal_proxy_limits import enforce_internal_rate_limit
from ..logging import get_logger
from ..workspaces import is_valid_workspace_id
from ..storage import (
    AttachmentStorageError,
    delete_objects,
    ensure_bucket,
    get_object_bytes,
    head_object,
    put_object_bytes,
)

router = APIRouter(prefix="/internal/attachments", tags=["attachments-proxy"])
log = get_logger("attachments_proxy")

_BLOB_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_FILE_OBJECT_RE = re.compile(r"^att_[\w-]+(?:\.[A-Za-z0-9._-]+)?$")


def _validate_file_put_key(*, object_key: str, workspace_id: str) -> None:
    _validate_object_key(object_key=object_key, workspace_id=workspace_id)
    ws = workspace_id.strip()
    prefix = f"{ws}/files/"
    if not object_key.startswith(prefix):
        raise HTTPException(status_code=400, detail="invalid file object key prefix")
    tail = object_key[len(prefix) :]
    if not _FILE_OBJECT_RE.fullmatch(tail):
        raise HTTPException(status_code=400, detail="invalid file object key name")


def _is_file_object_key(object_key: str, workspace_id: str) -> bool:
    ws = workspace_id.strip()
    return bool(ws) and object_key.startswith(f"{ws}/files/")


def _validate_blob_put_key(*, object_key: str, workspace_id: str) -> str:
    _validate_object_key(object_key=object_key, workspace_id=workspace_id)
    ws = workspace_id.strip()
    prefix = f"{ws}/blobs/"
    if not object_key.startswith(prefix):
        raise HTTPException(
            status_code=400,
            detail="PUT requires content-addressed blob key {workspace}/blobs/{sha256}",
        )
    digest = object_key[len(prefix) :]
    if not _BLOB_SHA256_RE.fullmatch(digest):
        raise HTTPException(status_code=400, detail="invalid sha256 in blob object key")
    return digest


def _assert_body_matches_key_digest(*, data: bytes, expected_digest: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_digest:
        raise HTTPException(
            status_code=400,
            detail="object key sha256 does not match request body",
        )


async def _assert_workspace_exists(*, workspace_id: str) -> None:
    ws = workspace_id.strip()
    if not is_valid_workspace_id(ws):
        raise HTTPException(status_code=400, detail="invalid workspace id")
    async with get_session() as session:
        owned = (
            await session.execute(
                select(Workspace.id).where(Workspace.id == ws).limit(1)
            )
        ).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=403, detail="workspace not found")


def _validate_object_key(*, object_key: str, workspace_id: str) -> None:
    key = object_key.strip()
    ws = workspace_id.strip()
    if not key or not ws:
        raise HTTPException(status_code=400, detail="object_key and workspace required")
    expected = f"{ws}/"
    legacy = f"attachments/{ws}/"
    if ".." in key or not (key.startswith(expected) or key.startswith(legacy)):
        raise HTTPException(status_code=403, detail="object_key not allowed for workspace")


async def _guard_attachment_access(*, workspace_id: str, object_key: str) -> None:
    await _assert_workspace_exists(workspace_id=workspace_id)
    _validate_object_key(object_key=object_key, workspace_id=workspace_id)


@router.post("/ensure-bucket")
async def attachments_ensure_bucket(
    _auth: None = Depends(require_agent_internal),
) -> dict:
    await enforce_internal_rate_limit(bucket="attachments")
    settings = get_settings()
    if settings.attachment_storage != "local":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    try:
        ensure_bucket()
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


@router.put("/objects")
async def attachments_put(
    request: Request,
    x_object_key: str = Header(..., alias="X-Object-Key"),
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
    content_type: str = Header(default="application/octet-stream", alias="Content-Type"),
    _auth: None = Depends(require_agent_internal),
) -> dict:
    ws = x_workspace_id.strip()
    await enforce_internal_rate_limit(bucket="attachments", workspace_id=ws)
    settings = get_settings()
    if settings.attachment_storage != "local":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    await _guard_attachment_access(
        workspace_id=x_workspace_id,
        object_key=x_object_key,
    )
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty body")
    max_bytes = settings.attachment_max_bytes
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"object exceeds {max_bytes} bytes")
    key = x_object_key.strip()
    if _is_file_object_key(key, ws):
        _validate_file_put_key(object_key=key, workspace_id=x_workspace_id)
    else:
        expected_digest = _validate_blob_put_key(object_key=key, workspace_id=x_workspace_id)
        _assert_body_matches_key_digest(data=data, expected_digest=expected_digest)
    try:
        existing = head_object(key)
        if existing is not None:
            log.info("attachment_put_skipped", key=key, bytes=len(data))
            return {**existing, "skipped": True}
        meta = put_object_bytes(
            object_key=key,
            mime_type=content_type,
            data=data,
        )
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    log.info("attachment_put", key=key, bytes=len(data))
    return {**meta, "skipped": False}


@router.get("/objects")
async def attachments_get(
    key: str,
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
    _auth: None = Depends(require_agent_internal),
) -> Response:
    ws = x_workspace_id.strip()
    await enforce_internal_rate_limit(bucket="attachments", workspace_id=ws)
    settings = get_settings()
    if settings.attachment_storage != "local":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    await _guard_attachment_access(
        workspace_id=x_workspace_id,
        object_key=key,
    )
    try:
        data = get_object_bytes(key.strip())
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="not found")
    return Response(content=data, media_type="application/octet-stream")


class AttachmentDeleteIn(BaseModel):
    keys: list[str] = Field(default_factory=list)


@router.post("/delete")
async def attachments_delete(
    payload: AttachmentDeleteIn,
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
    _auth: None = Depends(require_agent_internal),
) -> dict:
    ws = x_workspace_id.strip()
    await enforce_internal_rate_limit(bucket="attachments", workspace_id=ws)
    settings = get_settings()
    if settings.attachment_storage != "local":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    max_keys = settings.attachment_delete_max_keys
    if len(payload.keys) > max_keys:
        raise HTTPException(status_code=400, detail=f"at most {max_keys} keys per delete")
    await _assert_workspace_exists(workspace_id=x_workspace_id)
    for k in payload.keys:
        _validate_object_key(object_key=k, workspace_id=x_workspace_id)
    try:
        delete_objects(payload.keys)
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    log.info("attachment_delete", count=len(payload.keys))
    return {"ok": True}
