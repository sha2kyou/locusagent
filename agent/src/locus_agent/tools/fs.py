"""文件类工具：read_file / search_files / write_file / patch（限定 workspace 内）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..db import run_in_thread
from ..workspace import workspace_data_dir
from .args import pick_str
from .base import Tool, ToolError, ToolResult, register_builtin

MAX_READ_BYTES = 512 * 1024
MAX_WRITE_BYTES = 2 * 1024 * 1024


def _root() -> Path:
    return workspace_data_dir() / "workspace"


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
    rel = pick_str(args, "path", "file_path")
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


async def _write_file(args: dict[str, Any]) -> ToolResult:
    rel = pick_str(args, "path", "file_path")
    content = args.get("content")
    if content is None:
        content = args.get("file_content")
    if content is None:
        content = args.get("text")
    if content is None:
        raise ToolError("content is required")
    text = str(content)
    append = bool(args.get("append", False))
    create_dirs = bool(args.get("create_dirs", True))
    if len(text.encode("utf-8")) > MAX_WRITE_BYTES:
        raise ToolError(f"content too large (> {MAX_WRITE_BYTES} bytes)")
    p = _resolve(rel)
    if p.exists() and p.is_dir():
        raise ToolError(f"path is a directory: {rel}")

    def _do() -> str:
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        elif not p.parent.exists():
            raise ToolError(f"parent directory not found: {p.parent}")
        mode = "a" if append else "w"
        with p.open(mode, encoding="utf-8") as f:
            f.write(text)
        return f"{'appended' if append else 'written'}: {p.relative_to(_root())}"

    return ToolResult(content=await run_in_thread(_do))


async def _patch_file(args: dict[str, Any]) -> ToolResult:
    rel = pick_str(args, "path", "file_path")
    old_string = args.get("old_string")
    if old_string is None:
        old_string = args.get("old_text")
    new_string = args.get("new_string")
    if new_string is None:
        new_string = args.get("new_content")
    if new_string is None:
        new_string = args.get("content")
    replace_all = bool(args.get("replace_all", False))
    if not rel:
        raise ToolError("path is required")
    if old_string is None or str(old_string) == "":
        raise ToolError("old_string is required")
    if new_string is None:
        raise ToolError("new_string is required (use empty string to delete)")
    p = _resolve(rel)
    if not p.is_file():
        raise ToolError(f"not a file: {rel}")

    def _do() -> str:
        text = p.read_text(encoding="utf-8", errors="ignore")
        needle = str(old_string)
        replacement = str(new_string)
        count = text.count(needle)
        if count < 1:
            raise ToolError("old_string not found")
        if not replace_all and count > 1:
            raise ToolError("old_string matched multiple sections; provide more context or set replace_all=true")
        patched = text.replace(needle, replacement, -1 if replace_all else 1)
        p.write_text(patched, encoding="utf-8")
        applied = count if replace_all else 1
        return (
            f"patched: {p.relative_to(_root())} "
            f"({applied} replacement{'s' if applied != 1 else ''})"
        )

    return ToolResult(content=await run_in_thread(_do))


async def _delete_file(args: dict[str, Any]) -> ToolResult:
    rel = pick_str(args, "path", "file_path")
    if not rel:
        raise ToolError("path is required")
    p = _resolve(rel)
    if not p.exists():
        raise ToolError(f"not found: {rel}")
    if p.is_dir():
        raise ToolError(f"path is a directory: {rel}")

    def _do() -> str:
        p.unlink()
        return f"deleted: {p.relative_to(_root())}"

    return ToolResult(content=await run_in_thread(_do))


register_builtin(
    Tool(
        name="read_file",
        description=(
            "Read a workspace text file; returns `line|content` with offset/limit paging."
            "Prefer over cat/head/tail in terminal."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to workspace"},
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
            "Search file content or names within the workspace."
            "target=content: regex search; target=files: glob files."
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

register_builtin(
    Tool(
        name="write_file",
        description=(
            "Write a workspace file. Overwrite or append; creates parent dirs by default."
            "Path must be under workspace."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target file path relative to workspace"},
                "file_path": {"type": "string", "description": "Alias for path."},
                "content": {"type": "string", "description": "Content to write"},
                "file_content": {"type": "string", "description": "Alias for content."},
                "append": {"type": "boolean", "default": False},
                "create_dirs": {"type": "boolean", "default": True},
            },
            "required": ["content"],
        },
        handler=_write_file,
    )
)

register_builtin(
    Tool(
        name="patch",
        description=(
            "Targeted text replace in a workspace file. One match by default; replace_all=true for all."
            "Path must be under workspace."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target file path relative to workspace"},
                "file_path": {"type": "string", "description": "Alias for path."},
                "old_string": {"type": "string", "description": "Text to find"},
                "new_string": {"type": "string", "description": "Replacement text; empty string deletes"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["old_string", "new_string"],
        },
        handler=_patch_file,
    )
)


register_builtin(
    Tool(
        name="delete_file",
        description="Delete a file under workspace. Directories not supported.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target file path relative to workspace"},
                "file_path": {"type": "string", "description": "Alias for path."},
            },
            "required": ["path"],
        },
        handler=_delete_file,
    )
)
