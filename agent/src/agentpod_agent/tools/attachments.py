"""本地附件存储：按 attachment id 查询、下载与删除。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..core.persistence import (
    delete_attachment_by_id,
    get_attachment_detail,
    get_attachment_download,
)
from ..core.run_context import get_chat_session_id
from ..db import run_in_thread
from .args import pick_action, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin
from .fs import _resolve as resolve_workspace_path


def _format_attachment_detail(detail: dict[str, Any]) -> str:
    payload = {k: v for k, v in detail.items() if v is not None and v != ""}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _safe_filename(name: str) -> str:
    base = Path(str(name or "download").strip()).name or "download"
    cleaned = re.sub(r"[^\w.\- ]", "_", base).strip("._ ")
    return (cleaned or "download")[:200]


async def _download_to_workspace(attachment_id: str, rel_path: str) -> ToolResult:
    row = await get_attachment_download(attachment_id)
    if row is None:
        raise ToolError(f"attachment missing or unreadable: {attachment_id}")
    name, mime, data = row
    max_bytes = max(1, int(get_settings().attachment_max_bytes))
    if len(data) > max_bytes:
        raise ToolError(f"attachment exceeds size limit ({max_bytes} bytes)")

    target_rel = rel_path or f"downloads/{attachment_id}_{_safe_filename(name)}"
    target = resolve_workspace_path(target_rel)
    target.parent.mkdir(parents=True, exist_ok=True)

    def _write() -> tuple[str, int]:
        target.write_bytes(data)
        return target_rel, len(data)

    try:
        written_rel, size = await run_in_thread(_write)
    except OSError as exc:
        raise ToolError(f"write failed: {exc}") from exc

    return ToolResult(
        content=f"Downloaded to workspace/{written_rel} ({size} bytes, {mime})",
        metadata={
            "path": written_rel,
            "name": name,
            "mimeType": mime,
            "sizeBytes": size,
            "attachmentId": attachment_id,
        },
    )


async def _deliver_to_chat(attachment_id: str) -> ToolResult:
    if not get_chat_session_id():
        raise ToolError("deliver requires an active chat session")

    detail = await get_attachment_detail(attachment_id)
    if detail is None:
        raise ToolError(f"attachment not found: {attachment_id}")

    att_name = str(detail.get("name") or "attachment")
    return ToolResult(
        content="Attached to this reply; UI shows a download chip. Do not write sent, filename, or links in body.",
        metadata={"chat_attachment": {"id": attachment_id, "name": att_name}},
    )


async def _attachments_tool(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    attachment_id = pick_str(args, "id")
    if not attachment_id:
        raise ToolError("missing id parameter (attachment id, e.g. att_xxx)")

    if action == "get":
        detail = await get_attachment_detail(attachment_id)
        if detail is None:
            raise ToolError(f"attachment not found: {attachment_id}")
        return ToolResult(
            content=_format_attachment_detail(detail),
            metadata={"attachment": detail},
        )

    if action == "download":
        rel_path = pick_str(args, "path")
        return await _download_to_workspace(attachment_id, rel_path)

    if action == "deliver":
        return await _deliver_to_chat(attachment_id)

    if action == "delete":
        deleted = await delete_attachment_by_id(attachment_id)
        if not deleted:
            raise ToolError(f"attachment not found: {attachment_id}")
        return ToolResult(content=f"Deleted attachment {attachment_id}")

    raise ToolError(f"unknown action: {action}; supported: get / download / deliver / delete")


register_builtin(
    Tool(
        name="attachments",
        description=(
            "Query, download, or delete local attachments by id (e.g. att_xxx)."
            "For metadata checks, saving to workspace/ for read_file, "
            "delivering downloads to the user, or deleting unneeded files."
            "Actions: get / download to workspace / deliver to this reply for user download / delete. "
            "get returns metadata; text includes textPreview; images mark imageAvailable. "
            "download defaults to downloads/{id}_{filename}; path sets workspace-relative target. "
            "After deliver, do not mention filename or links in reply. "
            "delete removes DB record, message links, and local file when unreferenced."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get",
                        "download",
                        "deliver",
                        "delete",
                    ],
                },
                "id": {
                    "type": "string",
                    "description": "Attachment id (att_xxx) from [user attachment] line in chat or get result.",
                },
                "path": {
                    "type": "string",
                    "description": "Relative workspace path for download (default downloads/{id}_{filename}).",
                },
            },
            "required": ["action", "id"],
        },
        handler=_attachments_tool,
    )
)
