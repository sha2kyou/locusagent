"""minio 工具与附件按 id 删除逻辑测试。"""

from __future__ import annotations

from agentpod_agent.core.persistence import _unreferenced_object_keys
from agentpod_agent.tools.base import ToolError
from agentpod_agent.tools.minio import _format_attachment_detail, _minio_tool, _safe_filename


def test_unreferenced_object_keys_after_single_delete():
    class FakeCursor:
        def execute(self, _sql: str, params: tuple[str]):
            self.key = params[0]
            return self

        def fetchone(self):
            return {"n": 0}

    c = FakeCursor()
    assert _unreferenced_object_keys(c, ["attachments/ws1/blobs/abc"]) == ["attachments/ws1/blobs/abc"]


def test_format_attachment_detail_omits_empty_fields():
    text = _format_attachment_detail(
        {
            "id": "att_test",
            "name": "a.txt",
            "kind": "text",
            "mimeType": "text/plain",
            "sizeBytes": 3,
            "objectKey": "",
            "processable": True,
        }
    )
    assert '"id": "att_test"' in text
    assert "objectKey" not in text


async def test_minio_tool_requires_id():
    try:
        await _minio_tool({"action": "get"})
        assert False, "expected ToolError"
    except ToolError as exc:
        assert "id" in str(exc)


async def test_minio_tool_unknown_action():
    try:
        await _minio_tool({"action": "put", "id": "att_x"})
        assert False, "expected ToolError"
    except ToolError as exc:
        assert "未知 action" in str(exc)


def test_safe_filename_strips_unsafe_chars():
    assert _safe_filename("../../evil.pdf") == "evil.pdf"
    assert _safe_filename("截图 (1).png") == "截图 _1_.png"
