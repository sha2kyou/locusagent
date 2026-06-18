"""附件 hydrate 时对误分类文本的纠正。"""

from __future__ import annotations

import pytest

from locus_agent.core.persistence import _hydrate_attachment


@pytest.mark.asyncio
async def test_hydrate_reclassifies_utf8_other_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "# SideScript 2.0\nhello\n"

    async def _fake_resolve(_object_key: str, *, content_sha256: str | None = None):
        return text.encode("utf-8"), _object_key

    monkeypatch.setattr(
        "locus_agent.core.persistence.resolve_attachment_bytes",
        _fake_resolve,
    )

    out = await _hydrate_attachment(
        {
            "id": "att_test",
            "name": "rules.sidescript",
            "kind": "other",
            "mimeType": "application/octet-stream",
            "objectKey": "ws_test/blobs/abc",
            "sha256": "a" * 64,
            "processable": False,
            "unsupportedReason": "当前支持文本、图片、Excel（.xlsx）与 Word（.docx）附件",
            "truncated": False,
        }
    )

    assert out["kind"] == "text"
    assert out["processable"] is True
    assert out["unsupportedReason"] is None
    assert "SideScript" in str(out["text"])


@pytest.mark.asyncio
async def test_create_attachment_requires_content_for_nonempty_size() -> None:
    from locus_agent.core.persistence import create_attachment

    with pytest.raises(ValueError, match="attachment content required"):
        await create_attachment(
            session_id=None,
            kind="other",
            name="rules.sidescript",
            mime_type="application/octet-stream",
            size_bytes=100,
            text_content=None,
            image_data_url=None,
            file_data_base64=None,
            processable=False,
            unsupported_reason="legacy",
            truncated=False,
        )
