"""附件对象存储代理：S3 凭据仅留在 Host。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from sqlalchemy import select

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..db import User, Workspace, get_session
from ..internal_proxy_limits import audit_internal_proxy, enforce_internal_rate_limit
from ..logging import get_logger
from ..workspaces import is_valid_workspace_id
from ..storage import (
    AttachmentStorageError,
    delete_objects,
    ensure_bucket,
    get_object_bytes,
    put_object_bytes,
)

router = APIRouter(prefix="/internal/attachments", tags=["attachments-proxy"])
log = get_logger("attachments_proxy")

_KEY_PREFIX = "attachments/"


async def _assert_workspace_owned(*, user_id: int, workspace_id: str) -> None:
    ws = workspace_id.strip()
    if not is_valid_workspace_id(ws):
        raise HTTPException(status_code=400, detail="invalid workspace id")
    async with get_session() as session:
        owned = (
            await session.execute(
                select(Workspace.id).where(Workspace.user_id == user_id, Workspace.id == ws).limit(1)
            )
        ).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=403, detail="workspace not owned by user")


def _validate_object_key(*, object_key: str, workspace_id: str) -> None:
    key = object_key.strip()
    ws = workspace_id.strip()
    if not key or not ws:
        raise HTTPException(status_code=400, detail="object_key and workspace required")
    expected = f"{_KEY_PREFIX}{ws}/"
    if not key.startswith(expected) or ".." in key:
        raise HTTPException(status_code=403, detail="object_key not allowed for workspace")


async def _guard_attachment_access(*, user_id: int, workspace_id: str, object_key: str) -> None:
    await _assert_workspace_owned(user_id=user_id, workspace_id=workspace_id)
    _validate_object_key(object_key=object_key, workspace_id=workspace_id)


@router.post("/ensure-bucket")
async def attachments_ensure_bucket(
    user: User = Depends(require_agent_internal),
) -> dict:
    await enforce_internal_rate_limit(user_id=user.id, bucket="attachments")
    settings = get_settings()
    if settings.attachment_storage != "minio":
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
    user: User = Depends(require_agent_internal),
) -> dict:
    await enforce_internal_rate_limit(user_id=user.id, bucket="attachments")
    settings = get_settings()
    if settings.attachment_storage != "minio":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    await _guard_attachment_access(
        user_id=user.id,
        workspace_id=x_workspace_id,
        object_key=x_object_key,
    )
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty body")
    max_bytes = settings.attachment_max_bytes
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"object exceeds {max_bytes} bytes")
    try:
        meta = put_object_bytes(
            object_key=x_object_key.strip(),
            mime_type=content_type,
            data=data,
        )
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    log.info("attachment_put", user_id=user.id, key=x_object_key, bytes=len(data))
    await audit_internal_proxy(
        "proxy.attachment.put",
        user_id=user.id,
        detail={"bytes": len(data)},
    )
    return meta


@router.get("/objects")
async def attachments_get(
    key: str,
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
    user: User = Depends(require_agent_internal),
) -> Response:
    await enforce_internal_rate_limit(user_id=user.id, bucket="attachments")
    settings = get_settings()
    if settings.attachment_storage != "minio":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    await _guard_attachment_access(
        user_id=user.id,
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
    user: User = Depends(require_agent_internal),
) -> dict:
    await enforce_internal_rate_limit(user_id=user.id, bucket="attachments")
    settings = get_settings()
    if settings.attachment_storage != "minio":
        raise HTTPException(status_code=503, detail="attachment storage not enabled")
    max_keys = settings.attachment_delete_max_keys
    if len(payload.keys) > max_keys:
        raise HTTPException(status_code=400, detail=f"at most {max_keys} keys per delete")
    await _assert_workspace_owned(user_id=user.id, workspace_id=x_workspace_id)
    for k in payload.keys:
        _validate_object_key(object_key=k, workspace_id=x_workspace_id)
    try:
        delete_objects(payload.keys)
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    log.info("attachment_delete", user_id=user.id, count=len(payload.keys))
    await audit_internal_proxy(
        "proxy.attachment.delete",
        user_id=user.id,
        detail={"count": len(payload.keys)},
    )
    return {"ok": True}
