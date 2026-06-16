"""附件图片格式与 blob 去重测试。"""

from agentpod_agent.core.attachment_images import (
    UNSUPPORTED_IMAGE_REASON,
    detect_image_mime,
    validate_processable_image,
)
from agentpod_agent.core.persistence import _find_existing_blob, _unreferenced_object_keys


def test_detect_png():
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    assert detect_image_mime(data) == "image/png"


def test_detect_jpeg():
    assert detect_image_mime(b"\xff\xd8\xff" + b"\x00" * 8) == "image/jpeg"


def test_reject_svg_as_unprocessable():
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    ok, _mime, reason = validate_processable_image(svg, "image/svg+xml")
    assert ok is False
    assert reason == UNSUPPORTED_IMAGE_REASON


def test_accept_webp():
    data = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 4
    ok, mime, reason = validate_processable_image(data, "image/webp")
    assert ok is True
    assert mime == "image/webp"
    assert reason is None


def test_find_existing_blob_by_sha256():
    digest = "d" * 64
    canonical = f"ws1/blobs/{digest}"

    class FakeCursor:
        def __init__(self) -> None:
            self.row = {"object_key": "attachments/ws1/att_a/image/abc", "object_etag": "etag1"}

        def execute(self, _sql: str, _params: tuple[str, ...]):
            return self

        def fetchone(self):
            return self.row

    found = _find_existing_blob(
        FakeCursor(),
        sha256=digest,
        kind="image",
        canonical_key=canonical,
    )
    assert found == ("attachments/ws1/att_a/image/abc", "etag1")


def test_unreferenced_object_keys():
    class FakeCursor:
        def execute(self, _sql: str, params: tuple[str]):
            self.key = params[0]
            return self

        def fetchone(self):
            return {"n": 0 if self.key == "orphan" else 2}

    c = FakeCursor()
    assert _unreferenced_object_keys(c, ["orphan", "shared", "orphan"]) == ["orphan"]
