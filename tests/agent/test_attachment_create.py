"""create_attachment Office / 大小限制测试。"""

from __future__ import annotations

import base64
import io

import pytest
from openpyxl import Workbook

from agentpod_agent.core.persistence import create_attachment
from agentpod_agent.db import init_db
from agentpod_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()


def _minimal_xlsx_b64() -> str:
    wb = Workbook()
    ws = wb.active
    ws.append(["A", "B"])
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.mark.asyncio
async def test_create_attachment_rejects_oversized_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentpod_agent import config as config_mod

    settings = config_mod.get_settings()
    monkeypatch.setattr(settings, "attachment_max_bytes", 8)

    with pytest.raises(ValueError, match="attachment limit"):
        await create_attachment(
            session_id=None,
            kind="other",
            name="big.xlsx",
            mime_type=None,
            size_bytes=100,
            text_content=None,
            image_data_url=None,
            file_data_base64=base64.b64encode(b"x" * 100).decode("ascii"),
            processable=True,
            unsupported_reason=None,
            truncated=False,
        )


@pytest.mark.asyncio
async def test_create_attachment_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="invalid file_data_base64"):
        await create_attachment(
            session_id=None,
            kind="other",
            name="bad.xlsx",
            mime_type=None,
            size_bytes=0,
            text_content=None,
            image_data_url=None,
            file_data_base64="not-valid-base64!!!",
            processable=True,
            unsupported_reason=None,
            truncated=False,
        )


@pytest.mark.asyncio
async def test_create_attachment_office_parse_failure_skips_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    uploads: list[dict] = []

    async def _fake_save(**kwargs: object) -> dict:
        uploads.append(dict(kwargs))
        return {"object_key": "test/key", "etag": "etag", "skipped": False}

    monkeypatch.setattr(
        "agentpod_agent.core.persistence.save_attachment_bytes",
        _fake_save,
    )

    item = await create_attachment(
        session_id=None,
        kind="other",
        name="broken.xlsx",
        mime_type=None,
        size_bytes=4,
        text_content=None,
        image_data_url=None,
        file_data_base64=base64.b64encode(b"fake").decode("ascii"),
        processable=True,
        unsupported_reason=None,
        truncated=False,
    )

    assert uploads == []
    assert item["processable"] is False
    assert item["unsupportedReason"]


@pytest.mark.asyncio
async def test_create_attachment_office_stores_extracted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentpod_agent.core.attachment_documents import OFFICE_EXTRACTED_MIME

    uploads: list[dict] = []
    stored: dict[str, bytes] = {}

    async def _fake_save(**kwargs: object) -> dict:
        payload = dict(kwargs)
        uploads.append(payload)
        data = payload["data"]
        assert isinstance(data, bytes)
        stored["data"] = data
        return {"object_key": "blobs/ab/cd/test", "etag": "etag", "skipped": False}

    async def _fake_resolve(_object_key: str, *, content_sha256: str | None = None) -> tuple[bytes | None, str | None]:
        return stored.get("data"), _object_key

    monkeypatch.setattr(
        "agentpod_agent.core.persistence.save_attachment_bytes",
        _fake_save,
    )
    monkeypatch.setattr(
        "agentpod_agent.core.persistence.resolve_attachment_bytes",
        _fake_resolve,
    )

    item = await create_attachment(
        session_id=None,
        kind="text",
        name="sheet.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=0,
        text_content=None,
        image_data_url=None,
        file_data_base64=_minimal_xlsx_b64(),
        processable=True,
        unsupported_reason=None,
        truncated=False,
    )

    assert len(uploads) == 1
    assert uploads[0]["mime_type"] == OFFICE_EXTRACTED_MIME
    assert item["processable"] is True
    assert item["text"] is not None
    assert "A" in item["text"]
