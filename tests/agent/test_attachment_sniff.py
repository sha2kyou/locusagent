"""附件内容嗅探测试。"""

from __future__ import annotations

from agentpod_agent.core.attachment_sniff import (
    classify_uploaded_bytes,
    is_likely_utf8_text,
)


def test_is_likely_utf8_text_rejects_binary():
    assert is_likely_utf8_text(b"\x00\x01\x02") is False
    assert is_likely_utf8_text(b"PK\x03\x04") is False


def test_is_likely_utf8_text_accepts_plain_text():
    assert is_likely_utf8_text(b"# SideScript 2.0\nhello") is True


def test_classify_custom_text_extension():
    data = b"# SideScript 2.0\nTEMPLATE @CSVM3\n"
    out = classify_uploaded_bytes(data=data, name="rules.sidescript", mime_type="")
    assert out.kind == "text"
    assert out.processable is True
    assert out.raw == data
    assert out.text_content is not None


def test_classify_pdf_as_binary():
    data = b"%PDF-1.4\n%binary\xff"
    out = classify_uploaded_bytes(data=data, name="doc.pdf", mime_type="application/pdf")
    assert out.kind == "other"
    assert out.processable is False
    assert out.raw == data


def test_classify_png_as_image():
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    out = classify_uploaded_bytes(data=data, name="x.png", mime_type="image/png")
    assert out.kind == "image"
    assert out.processable is True
