"""将 workspace 内生成的文件交付到对话，供用户下载。"""

from __future__ import annotations

import mimetypes
from typing import Any

from ..config import get_settings
from ..core.persistence import create_binary_attachment
from ..core.run_context import get_chat_session_id
from ..db import run_in_thread
from .args import pick_str
from .base import Tool, ToolError, ToolResult, register_builtin
from .fs import _resolve as resolve_workspace_path


def _guess_mime(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


async def _deliver_file(args: dict[str, Any]) -> ToolResult:
    session_id = get_chat_session_id()
    if not session_id:
        raise ToolError("deliver_file requires an active chat session")

    rel = pick_str(args, "path", "file_path")
    path = resolve_workspace_path(rel)
    if not path.is_file():
        raise ToolError(f"not a file: {rel}")

    max_bytes = max(1, int(get_settings().attachment_max_bytes))

    def _read() -> tuple[bytes, str]:
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise ToolError(f"file exceeds attachment limit ({max_bytes} bytes)")
        display_name = str(args.get("name") or "").strip() or path.name
        return data, display_name

    try:
        data, display_name = await run_in_thread(_read)
    except ToolError:
        raise
    except OSError as exc:
        raise ToolError(f"read failed: {exc}") from exc

    mime = str(args.get("mime_type") or "").strip() or _guess_mime(display_name)
    try:
        att = await create_binary_attachment(
            session_id=session_id,
            name=display_name,
            mime_type=mime,
            data=data,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except RuntimeError as exc:
        raise ToolError(str(exc)) from exc

    att_id = str(att.get("id") or "")
    att_name = str(att.get("name") or display_name)
    return ToolResult(
        content=f"Delivered file to user chat: {att_name} (id={att_id}). Mention it briefly in your reply.",
        metadata={"chat_attachment": {"id": att_id, "name": att_name}},
    )


register_builtin(
    Tool(
        name="deliver_file",
        description=(
            "Attach a workspace file to the current assistant reply for user download in chat. "
            "Use after generating exports (PDF, zip, csv, binaries, etc.) under workspace/. "
            "Does not send file bytes to the model."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to workspace/ (e.g. exports/report.pdf)",
                },
                "name": {
                    "type": "string",
                    "description": "Download filename shown to the user (defaults to basename of path)",
                },
                "mime_type": {
                    "type": "string",
                    "description": "Optional MIME type (auto-guessed from name if omitted)",
                },
            },
            "required": ["path"],
        },
        handler=_deliver_file,
    )
)
