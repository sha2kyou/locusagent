"""Host 侧 MinIO（S3 兼容）附件存储。"""

from __future__ import annotations

import io
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from ..config import Settings, get_settings
from ..logging import get_logger

log = get_logger("host_s3")


class AttachmentStorageError(RuntimeError):
    pass


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


def _bucket(settings: Settings | None = None) -> str:
    return (settings or get_settings()).s3_bucket


def ensure_bucket(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    client = _client()
    bucket = _bucket(s)
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except Exception as exc:
        raise AttachmentStorageError(f"ensure bucket failed: {exc}") from exc


def put_object_bytes(
    *,
    object_key: str,
    mime_type: str,
    data: bytes,
    settings: Settings | None = None,
) -> dict[str, str]:
    s = settings or get_settings()
    ensure_bucket(s)
    try:
        result = _client().put_object(
            bucket_name=_bucket(s),
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=mime_type,
        )
        return {"object_key": object_key, "etag": str(result.etag or "").strip('"')}
    except Exception as exc:
        raise AttachmentStorageError(f"put object failed: {exc}") from exc


def get_object_bytes(object_key: str, settings: Settings | None = None) -> bytes | None:
    if not object_key:
        return None
    s = settings or get_settings()
    try:
        resp = _client().get_object(bucket_name=_bucket(s), object_name=object_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchBucket"}:
            return None
        raise AttachmentStorageError(f"get object failed: {exc}") from exc
    except Exception as exc:
        raise AttachmentStorageError(f"get object failed: {exc}") from exc
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def delete_objects(object_keys: list[str], settings: Settings | None = None) -> None:
    keys = [k for k in object_keys if k]
    if not keys:
        return
    s = settings or get_settings()
    client = _client()
    bucket = _bucket(s)
    for key in keys:
        try:
            client.remove_object(bucket, key)
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchBucket"}:
                log.warning("attachment_delete_failed", key=key, error=str(exc))
        except Exception as exc:
            log.warning("attachment_delete_failed", key=key, error=str(exc))
