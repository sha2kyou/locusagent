"""本地文件附件存储（~/.agentpod/attachments）。"""

from __future__ import annotations

from pathlib import Path

from .settings_store import data_dir


class AttachmentStorageError(RuntimeError):
    pass


def _root() -> Path:
    path = data_dir() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _object_path(object_key: str) -> Path:
    key = object_key.strip().lstrip("/")
    if not key or ".." in key.split("/"):
        raise AttachmentStorageError("invalid object key")
    return _root() / key


def ensure_bucket() -> None:
    _root().mkdir(parents=True, exist_ok=True)


def head_object(object_key: str) -> dict[str, str] | None:
    if not object_key:
        return None
    path = _object_path(object_key)
    if not path.is_file():
        return None
    stat = path.stat()
    return {
        "object_key": object_key,
        "etag": f"{stat.st_size}-{int(stat.st_mtime)}",
    }


def put_object_bytes(*, object_key: str, mime_type: str, data: bytes) -> dict[str, str]:
    _ = mime_type
    ensure_bucket()
    path = _object_path(object_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stat = path.stat()
    return {
        "object_key": object_key,
        "etag": f"{stat.st_size}-{int(stat.st_mtime)}",
    }


def get_object_bytes(object_key: str) -> bytes | None:
    if not object_key:
        return None
    path = _object_path(object_key)
    if not path.is_file():
        return None
    return path.read_bytes()


def delete_objects(object_keys: list[str]) -> None:
    for key in object_keys:
        if not key:
            continue
        try:
            path = _object_path(key)
            if path.is_file():
                path.unlink()
        except Exception:
            continue
