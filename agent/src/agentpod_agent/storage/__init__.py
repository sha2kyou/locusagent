"""Object storage helpers for large binary payloads."""

from .attachments import (
    delete_attachment_objects,
    load_attachment_bytes,
    save_attachment_bytes,
)

__all__ = [
    "delete_attachment_objects",
    "load_attachment_bytes",
    "save_attachment_bytes",
]
