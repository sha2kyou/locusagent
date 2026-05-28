"""terminal 工具：P0 默认禁用。

启用条件（任一）：
- 环境变量 ENABLE_TERMINAL=1
- 命令必须命中白名单（TERMINAL_WHITELIST，逗号分隔）
- 单次执行超时 10s，输出截断 8KB
"""

from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from .base import Tool, ToolError, ToolResult, register_builtin

DEFAULT_TIMEOUT = 10.0
MAX_OUTPUT = 8 * 1024


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
    proc = await asyncio.create_subprocess_exec(
        *parts,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=DEFAULT_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ToolError(f"command timed out after {DEFAULT_TIMEOUT}s") from None
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
        description="执行 shell 命令（默认禁用，需 ENABLE_TERMINAL=1 + TERMINAL_WHITELIST）。",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        handler=_terminal,
        enabled=False,
        category="builtin",
    )
)
