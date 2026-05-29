"""terminal 工具：执行 shell 命令（受开关与白名单约束）。"""

from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from .base import Tool, ToolError, ToolResult, register_builtin

DEFAULT_TIMEOUT = 180.0
MAX_OUTPUT = 100 * 1024


def _enabled() -> bool:
    return os.environ.get("ENABLE_TERMINAL", "").lower() in ("1", "true", "yes")


def _whitelist() -> set[str]:
    raw = os.environ.get("TERMINAL_WHITELIST", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


async def _terminal(args: dict[str, Any]) -> ToolResult:
    if not _enabled():
        raise ToolError("terminal is disabled (set ENABLE_TERMINAL=1 to enable)")
    cmd = str(args.get("command", "")).strip()
    if not cmd:
        raise ToolError("command is required")
    parts = shlex.split(cmd)
    if not parts:
        raise ToolError("command is empty after parsing")
    head = parts[0]
    wl = _whitelist()
    if not wl:
        raise ToolError("TERMINAL_WHITELIST is empty; refuse to run anything")
    if head not in wl:
        raise ToolError(f"command '{head}' not in whitelist")
    timeout = float(args.get("timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)
    if timeout <= 0:
        raise ToolError("timeout must be > 0")
    workdir = args.get("workdir")
    cwd: str | None = None
    if workdir is not None:
        cwd = str(workdir).strip()
        if not cwd:
            raise ToolError("workdir cannot be empty")
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd or None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ToolError(f"command timed out after {timeout}s") from None
    text = (out or b"").decode("utf-8", errors="replace")
    truncated = text[:MAX_OUTPUT]
    note = "\n…(output truncated)" if len(text) > MAX_OUTPUT else ""
    return ToolResult(
        content=f"exit={proc.returncode}\n{truncated}{note}",
        metadata={"exit_code": proc.returncode},
    )


register_builtin(
    Tool(
        name="terminal",
        description=(
            "执行 shell 命令。用于构建、安装、git、进程管理与脚本执行。"
            "默认受 ENABLE_TERMINAL=1 与 TERMINAL_WHITELIST 白名单约束；"
            "不用于文件读写/搜索（优先 read_file 与 search_files）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "timeout": {"type": "number", "minimum": 0.1, "default": DEFAULT_TIMEOUT},
                "workdir": {"type": "string", "description": "可选工作目录（默认沿用当前目录）"},
            },
            "required": ["command"],
        },
        handler=_terminal,
        enabled=True,
        category="builtin",
    )
)
