"""文件类工具：read_file / search_files（限定 workspace 内）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..db import run_in_thread
from .base import Tool, ToolError, ToolResult, register_builtin

MAX_READ_BYTES = 512 * 1024


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
    offset = int(args.get("offset", 1) or 1)
    limit = int(args.get("limit", 500) or 500)
    if offset < 1:
        raise ToolError("offset must be >= 1")
    if limit < 1:
        raise ToolError("limit must be >= 1")
    if limit > 2000:
        limit = 2000
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
        start_idx = offset - 1
        end_idx = min(len(lines), start_idx + limit)
        chunk = lines[start_idx:end_idx]
        numbered = "\n".join(
            f"{lineno}|{line}" for lineno, line in enumerate(chunk, start=offset)
        )
        if not numbered:
            return "(empty range)"
        return numbered

    out = await run_in_thread(_do)
    return ToolResult(content=out)


async def _search_files(args: dict[str, Any]) -> ToolResult:
    pattern = str(args.get("pattern", "")).strip()
    target = str(args.get("target", "content") or "content").strip().lower()
    path = str(args.get("path", ".") or ".").strip()
    file_glob = str(args.get("file_glob", "**/*") or "**/*").strip() or "**/*"
    case_sensitive = bool(args.get("case_sensitive", False))
    output_mode = str(args.get("output_mode", "content") or "content").strip().lower()
    limit = int(args.get("limit", 50) or 50)
    offset = int(args.get("offset", 0) or 0)
    if not pattern:
        raise ToolError("pattern is required")
    if limit < 1:
        raise ToolError("limit must be >= 1")
    if offset < 0:
        raise ToolError("offset must be >= 0")
    base = _resolve(path)
    if not base.exists():
        raise ToolError(f"path not found: {path}")
    if base.is_file() and target == "files":
        raise ToolError("target=files requires a directory path")

    if target == "files":
        def _do_files() -> str:
            rows: list[tuple[float, str]] = []
            for p in base.glob(pattern):
                if p.is_file():
                    rel = p.relative_to(_root())
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    rows.append((mtime, str(rel)))
            rows.sort(key=lambda x: x[0], reverse=True)
            sliced = rows[offset : offset + limit]
            if not sliced:
                return "no matches"
            return "\n".join(item[1] for item in sliced)

        return ToolResult(content=await run_in_thread(_do_files))

    if target != "content":
        raise ToolError("target must be one of: content, files")

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        raise ToolError(f"invalid regex: {exc}") from exc
    def _do_content() -> str:
        matches: list[tuple[str, int, str]] = []
        hit_files: dict[str, int] = {}
        scan_iter = [base] if base.is_file() else list(base.glob(file_glob))
        for p in scan_iter:
            if not p.is_file():
                continue
            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        if regex.search(line):
                            rel = str(p.relative_to(_root()))
                            matches.append((rel, lineno, line.rstrip()))
                            hit_files[rel] = hit_files.get(rel, 0) + 1
            except OSError:
                continue
        if output_mode == "files_only":
            rows = sorted(hit_files.keys())
            sliced = rows[offset : offset + limit]
            return "\n".join(sliced) if sliced else "no matches"
        if output_mode == "count":
            rows = sorted(hit_files.items(), key=lambda x: x[0])
            sliced = rows[offset : offset + limit]
            if not sliced:
                return "no matches"
            return "\n".join(f"{f}: {n}" for f, n in sliced)
        if output_mode != "content":
            raise ToolError("output_mode must be one of: content, files_only, count")
        sliced = matches[offset : offset + limit]
        if not sliced:
            return "no matches"
        return "\n".join(f"{f}:{ln}: {txt}" for f, ln, txt in sliced)

    return ToolResult(content=await run_in_thread(_do_content))


register_builtin(
    Tool(
        name="read_file",
        description=(
            "读取工作区文本文件，返回 `行号|内容`，支持 offset/limit 分页。"
            "用于替代在 terminal 里用 cat/head/tail 读文件。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对 workspace 的路径"},
                "offset": {"type": "integer", "minimum": 1, "default": 1},
                "limit": {"type": "integer", "minimum": 1, "default": 500},
            },
            "required": ["path"],
        },
        handler=_read_file,
        enabled=True,
    )
)

register_builtin(
    Tool(
        name="search_files",
        description=(
            "在工作区内搜索内容或文件名。"
            "target=content 时按正则搜内容；target=files 时按 glob 找文件。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "target": {"type": "string", "enum": ["content", "files"], "default": "content"},
                "path": {"type": "string", "default": "."},
                "file_glob": {"type": "string", "default": "**/*"},
                "case_sensitive": {"type": "boolean", "default": False},
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_only", "count"],
                    "default": "content",
                },
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
            },
            "required": ["pattern"],
        },
        handler=_search_files,
    )
)
