"""文件类工具：read_file / write_file / patch / search_files。

所有路径限定在 /data/workspace 根下；越界一律拒绝。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..db import run_in_thread
from .base import Tool, ToolError, ToolResult, register_builtin

MAX_READ_BYTES = 256 * 1024
MAX_WRITE_BYTES = 1 * 1024 * 1024


def _root() -> Path:
    return get_settings().data_dir / "workspace"


def _resolve(rel: str) -> Path:
    if not rel:
        raise ToolError("path is required")
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ToolError(f"path escapes workspace: {rel}") from exc
    return candidate


async def _read_file(args: dict[str, Any]) -> ToolResult:
    rel = str(args.get("path", "")).strip()
    offset = int(args.get("offset", 0) or 0)
    limit = int(args.get("limit", 2000) or 2000)
    p = _resolve(rel)
    if not p.is_file():
        raise ToolError(f"not a file: {rel}")

    def _do() -> str:
        with p.open("rb") as f:
            data = f.read(MAX_READ_BYTES + 1)
        if len(data) > MAX_READ_BYTES:
            raise ToolError(f"file too large (> {MAX_READ_BYTES} bytes)")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        end = min(len(lines), offset + limit) if limit > 0 else len(lines)
        chunk = lines[offset:end]
        numbered = "\n".join(f"{i+1:>6}|{line}" for i, line in enumerate(chunk, start=offset))
        return f"# {rel} ({offset+1}..{end} / {len(lines)} lines)\n{numbered}"

    out = await run_in_thread(_do)
    return ToolResult(content=out)


async def _write_file(args: dict[str, Any]) -> ToolResult:
    rel = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ToolError(f"content too large (> {MAX_WRITE_BYTES} bytes)")
    p = _resolve(rel)

    def _do() -> str:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {rel}"

    out = await run_in_thread(_do)
    return ToolResult(content=out)


async def _patch(args: dict[str, Any]) -> ToolResult:
    rel = str(args.get("path", "")).strip()
    old = str(args.get("old", ""))
    new = str(args.get("new", ""))
    replace_all = bool(args.get("replace_all", False))
    if not old:
        raise ToolError("old must be non-empty")
    p = _resolve(rel)
    if not p.is_file():
        raise ToolError(f"not a file: {rel}")

    def _do() -> str:
        text = p.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            raise ToolError("old text not found")
        if not replace_all and count > 1:
            raise ToolError(f"old text occurs {count} times; pass replace_all=true or extend context")
        new_text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        p.write_text(new_text, encoding="utf-8")
        return f"patched {rel} ({'all' if replace_all else 'first'} occurrence(s), {count} matches)"

    out = await run_in_thread(_do)
    return ToolResult(content=out)


async def _search_files(args: dict[str, Any]) -> ToolResult:
    pattern = str(args.get("pattern", "")).strip()
    glob = str(args.get("glob", "**/*")).strip() or "**/*"
    case_sensitive = bool(args.get("case_sensitive", False))
    if not pattern:
        raise ToolError("pattern is required")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        raise ToolError(f"invalid regex: {exc}") from exc
    root = _root()
    root.mkdir(parents=True, exist_ok=True)

    def _do() -> str:
        hits: list[str] = []
        files_scanned = 0
        for p in root.glob(glob):
            if not p.is_file():
                continue
            files_scanned += 1
            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        if regex.search(line):
                            rel = p.relative_to(root)
                            hits.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(hits) >= 200:
                                break
            except OSError:
                continue
            if len(hits) >= 200:
                break
        if not hits:
            return f"no matches in {files_scanned} files"
        return "\n".join(hits[:200]) + ("\n…(truncated)" if len(hits) >= 200 else "")

    out = await run_in_thread(_do)
    return ToolResult(content=out)


register_builtin(
    Tool(
        name="read_file",
        description="读取工作区文件，支持按行分页。返回行号 + 内容。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对 workspace 的路径"},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "default": 2000},
            },
            "required": ["path"],
        },
        handler=_read_file,
    )
)

register_builtin(
    Tool(
        name="write_file",
        description="写入工作区文件，覆盖原内容；目录不存在时自动创建。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        handler=_write_file,
    )
)

register_builtin(
    Tool(
        name="patch",
        description="查找替换：默认要求 old 唯一；replace_all=true 替换所有。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string"},
                "new": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["path", "old", "new"],
        },
        handler=_patch,
    )
)

register_builtin(
    Tool(
        name="search_files",
        description="按正则在工作区中搜索文件内容。返回 path:line: snippet。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "glob": {"type": "string", "default": "**/*"},
                "case_sensitive": {"type": "boolean", "default": False},
            },
            "required": ["pattern"],
        },
        handler=_search_files,
    )
)
