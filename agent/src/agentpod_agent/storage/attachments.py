"""Attachment object storage using MinIO (S3 compatible)."""

from __future__ import annotations

import hashlib
import io
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from ..config import get_settings


@lru_cache
def _client() -> Minio:
    s = get_settings()
    return Minio(
        endpoint=s.s3_endpoint,
        access_key=s.s3_access_key,
        secret_key=s.s3_secret_key,
        secure=bool(s.s3_use_ssl),
        region=s.s3_region or None,
    )


def _bucket() -> str:
    return get_settings().s3_bucket


def _ensure_bucket() -> None:
    client = _client()
    bucket = _bucket()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _object_key(*, attachment_id: str, kind: str, name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return f"attachments/{attachment_id}/{kind}/{digest}"


def save_attachment_bytes(
    *,
    attachment_id: str,
    kind: str,
    name: str,
    mime_type: str,
    data: bytes,
) -> dict[str, str]:
    _ensure_bucket()
    key = _object_key(attachment_id=attachment_id, kind=kind, name=name)
    result = _client().put_object(
        bucket_name=_bucket(),
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )
    return {"object_key": key, "etag": str(result.etag or "").strip("\"")}


def load_attachment_bytes(object_key: str) -> bytes | None:
    if not object_key:
        return None
    try:
        resp = _client().get_object(bucket_name=_bucket(), object_name=object_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchBucket"}:
            return None
        raise
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def delete_attachment_objects(object_keys: list[str]) -> None:
    keys = [k for k in object_keys if k]
    if not keys:
        return
    client = _client()
    bucket = _bucket()
    for key in keys:
        try:
            client.remove_object(bucket, key)
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchBucket"}:
                raise
