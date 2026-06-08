"""附件存储：桌面单体使用本地文件。"""

from __future__ import annotations

from agentpod_shared import local_storage

AttachmentStorageError = local_storage.AttachmentStorageError
delete_objects = local_storage.delete_objects
ensure_bucket = local_storage.ensure_bucket
get_object_bytes = local_storage.get_object_bytes
head_object = local_storage.head_object
put_object_bytes = local_storage.put_object_bytes

__all__ = [
    "AttachmentStorageError",
    "delete_objects",
    "ensure_bucket",
    "get_object_bytes",
    "head_object",
    "put_object_bytes",
]
