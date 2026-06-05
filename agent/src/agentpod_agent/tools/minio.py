"""MinIO 附件存储：按 attachment id 查询、下载与删除。"""

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
        raise ToolError(f"附件不存在或无法读取: {attachment_id}")
    name, mime, data = row
    max_bytes = max(1, int(get_settings().attachment_max_bytes))
    if len(data) > max_bytes:
        raise ToolError(f"附件超过大小限制（{max_bytes} bytes）")

    target_rel = rel_path or f"downloads/{attachment_id}_{_safe_filename(name)}"
    target = resolve_workspace_path(target_rel)
    target.parent.mkdir(parents=True, exist_ok=True)

    def _write() -> tuple[str, int]:
        target.write_bytes(data)
        return target_rel, len(data)

    try:
        written_rel, size = await run_in_thread(_write)
    except OSError as exc:
        raise ToolError(f"写入失败: {exc}") from exc

    return ToolResult(
        content=f"已下载到 workspace/{written_rel}（{size} bytes，{mime}）",
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
        raise ToolError("deliver 需要活跃的对话会话")

    detail = await get_attachment_detail(attachment_id)
    if detail is None:
        raise ToolError(f"附件不存在: {attachment_id}")

    att_name = str(detail.get("name") or "附件")
    return ToolResult(
        content="已附加到当前回复，界面会显示下载标签。不要在正文中写已发送、文件名或任何链接。",
        metadata={"chat_attachment": {"id": attachment_id, "name": att_name}},
    )


async def _minio_tool(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    attachment_id = pick_str(args, "id", "attachment_id")
    if not attachment_id:
        raise ToolError("缺少 id 参数（attachment id，如 att_xxx）")

    if action in {"get", "query", "head", "info"}:
        detail = await get_attachment_detail(attachment_id)
        if detail is None:
            raise ToolError(f"附件不存在: {attachment_id}")
        return ToolResult(
            content=_format_attachment_detail(detail),
            metadata={"attachment": detail},
        )

    if action in {"download", "fetch", "save"}:
        rel_path = pick_str(args, "path", "file_path")
        return await _download_to_workspace(attachment_id, rel_path)

    if action in {"deliver", "attach"}:
        return await _deliver_to_chat(attachment_id)

    if action == "delete":
        deleted = await delete_attachment_by_id(attachment_id)
        if not deleted:
            raise ToolError(f"附件不存在: {attachment_id}")
        return ToolResult(content=f"已删除附件 {attachment_id}")

    raise ToolError(f"未知 action: {action}，支持 get / download / deliver / delete")


register_builtin(
    Tool(
        name="minio",
        description=(
            "查询、下载或删除 MinIO 中的用户附件（按 attachment id，如 att_xxx）。"
            "适用于核对附件元数据、将附件落盘到 workspace/ 供 read_file 等工具处理，"
            "或将已有附件交付给用户下载，或清理不再需要的存储对象。"
            "动作：get（查询，别名 query/head/info）/ download（落盘到 workspace，别名 fetch/save）/"
            "deliver（附加到当前回复供用户下载，别名 attach）/ delete。"
            "get 返回元数据；文本含 textPreview，图片仅标注 imageAvailable。"
            "download 默认写入 downloads/{id}_{文件名}，可用 path 指定 workspace 相对路径。"
            "deliver 成功后不要在回复中提及文件名或链接。"
            "delete 会移除数据库记录、消息关联，并在无引用时删除 MinIO 对象。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get",
                        "query",
                        "head",
                        "info",
                        "download",
                        "fetch",
                        "save",
                        "deliver",
                        "attach",
                        "delete",
                    ],
                },
                "id": {
                    "type": "string",
                    "description": "Attachment id（att_xxx），来自对话 [用户附件] 行或 get 结果。",
                },
                "path": {
                    "type": "string",
                    "description": "download 时写入 workspace/ 的相对路径（默认 downloads/{id}_{文件名}）。",
                },
            },
            "required": ["action", "id"],
        },
        handler=_minio_tool,
    )
)
