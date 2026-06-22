"""附件本地文件存储辅助：经 Host internal API 读写 ~/.locusagent/attachments。"""

from .attachments import (
    AttachmentStorageError,
    blob_object_key,
    delete_attachment_objects,
    file_object_key,
    load_attachment_bytes,
    resolve_attachment_bytes,
    save_attachment_bytes,
    save_attachment_file,
    upload_was_skipped,
)

__all__ = [
    "AttachmentStorageError",
    "blob_object_key",
    "delete_attachment_objects",
    "file_object_key",
    "load_attachment_bytes",
    "resolve_attachment_bytes",
    "save_attachment_bytes",
    "save_attachment_file",
    "upload_was_skipped",
]
