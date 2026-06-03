"""附件图片格式校验（与上游视觉模型支持范围对齐）。"""

from __future__ import annotations

SUPPORTED_IMAGE_MIMES = frozenset(
    {
        "image/bmp",
        "image/gif",
        "image/png",
        "image/jpeg",
        "image/webp",
    }
)

UNSUPPORTED_IMAGE_REASON = "仅支持 BMP/GIF/PNG/JPEG/WebP 图片格式"


def detect_image_mime(data: bytes) -> str | None:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"GIF":
        return "image/gif"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 2 and data[:2] == b"BM":
        return "image/bmp"
    return None


def validate_processable_image(data: bytes, declared_mime: str | None) -> tuple[bool, str, str | None]:
    detected = detect_image_mime(data)
    if detected is None or detected not in SUPPORTED_IMAGE_MIMES:
        mime = (declared_mime or "").split(";", 1)[0].strip().lower() or "application/octet-stream"
        return False, mime, UNSUPPORTED_IMAGE_REASON
    return True, detected, None
