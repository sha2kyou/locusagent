"""上传字节嗅探：存原文件，仅判断能否内联到模型上下文。"""

from __future__ import annotations

from dataclasses import dataclass

from .attachment_documents import (
    MAX_EXTRACT_CHARS,
    extract_document_text,
    is_office_attachment,
)
from .attachment_images import validate_processable_image

MAX_TEXT_EXTRACT_CHARS = MAX_EXTRACT_CHARS


@dataclass(frozen=True)
class ClassifiedUpload:
    kind: str
    processable: bool
    raw: bytes
    mime_type: str
    text_content: str | None = None
    unsupported_reason: str | None = None
    truncated: bool = False


def _truncate_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_EXTRACT_CHARS:
        return text, False
    return f"{text[:MAX_TEXT_EXTRACT_CHARS]}\n...（文件过长，已截断）", True


def is_likely_utf8_text(data: bytes) -> bool:
    if not data:
        return True
    if b"\x00" in data[:8192]:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text:
        return True
    control = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    return (control / len(text)) <= 0.02


def classify_uploaded_bytes(*, data: bytes, name: str, mime_type: str | None) -> ClassifiedUpload:
    clean_name = (name or "attachment").strip() or "attachment"
    clean_mime = str(mime_type or "").strip() or "application/octet-stream"
    raw = data

    ok_img, img_mime, _reason = validate_processable_image(raw, clean_mime)
    if ok_img:
        return ClassifiedUpload(
            kind="image",
            processable=True,
            raw=raw,
            mime_type=img_mime,
        )

    if is_office_attachment(name=clean_name, mime_type=clean_mime):
        extracted, doc_trunc, err = extract_document_text(
            raw,
            name=clean_name,
            mime_type=clean_mime,
        )
        if err is None and extracted.strip():
            text, text_trunc = _truncate_text(extracted)
            return ClassifiedUpload(
                kind="text",
                processable=True,
                raw=raw,
                mime_type=clean_mime,
                text_content=text,
                truncated=bool(doc_trunc or text_trunc),
            )

    if is_likely_utf8_text(raw):
        text = raw.decode("utf-8", errors="replace")
        text, truncated = _truncate_text(text)
        mime = clean_mime if clean_mime.startswith("text/") else "text/plain;charset=utf-8"
        return ClassifiedUpload(
            kind="text",
            processable=True,
            raw=raw,
            mime_type=mime,
            text_content=text,
            truncated=truncated,
        )

    return ClassifiedUpload(
        kind="other",
        processable=False,
        raw=raw,
        mime_type=clean_mime,
    )
