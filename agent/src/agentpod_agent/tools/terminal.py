"""terminal 工具：执行 shell 命令（受开关与白名单约束）。"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..subprocess_sandbox import (
    build_sandbox_preexec_fn,
    resolve_workdir,
    should_restrict_terminal_workdir,
    terminate_process_tree,
)
from ..subprocess_env import safe_subprocess_env
from .base import Tool, ToolError, ToolResult, register_builtin

DEFAULT_TIMEOUT = 180.0
MAX_OUTPUT = 100 * 1024


def _command_set(raw: str) -> set[str]:
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _enabled() -> bool:
    return get_settings().enable_terminal


def _whitelist() -> set[str]:
    return _command_set(get_settings().terminal_whitelist)


def _denylist() -> set[str]:
    return _command_set(get_settings().terminal_denylist)


async def _terminal(args: dict[str, Any]) -> ToolResult:
    if not _enabled():
        raise ToolError("terminal 已禁用，请在 设置 → 工具 中开启")
    cmd = str(args.get("command", "")).strip()
    if not cmd:
        raise ToolError("command is required")
    try:
        parts = shlex.split(cmd)
    except ValueError as exc:
        raise ToolError(f"invalid command syntax: {exc}") from exc
    if not parts:
        raise ToolError("command is empty after parsing")
    raw_head = str(parts[0]).strip()
    head = Path(raw_head).name.lower()
    if "/" in raw_head or "\\" in raw_head:
        raise ToolError("command must be a bare executable name, path is not allowed")
    wl = _whitelist()
    if not wl:
        raise ToolError("terminal 白名单为空，请在 设置 → 工具 中配置允许执行的命令")
    if head not in wl:
        raise ToolError(f"command '{head}' not in whitelist")
    if head in _denylist():
        raise ToolError(f"command '{head}' is blocked by TERMINAL_DENYLIST")
    resolved = shutil.which(head, path=safe_subprocess_env().get("PATH"))
    if not resolved:
        raise ToolError(f"command '{head}' not found in PATH")
    exec_name = Path(resolved).name.lower()
    if exec_name != head:
        raise ToolError(f"resolved executable mismatch for command '{head}'")
    timeout = float(args.get("timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)
    if timeout <= 0:
        raise ToolError("timeout must be > 0")
    restrict_workspace = should_restrict_terminal_workdir()
    try:
        base_cwd = resolve_workdir(None, restrict_to_workspace=restrict_workspace)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    workdir = args.get("workdir")
    cwd = str(base_cwd)
    if workdir is not None:
        candidate = str(workdir).strip()
        if not candidate:
            raise ToolError("workdir cannot be empty")
        try:
            resolved = resolve_workdir(
                candidate,
                restrict_to_workspace=restrict_workspace,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        cwd = str(resolved)
    preexec_fn = build_sandbox_preexec_fn()
    exec_parts = [resolved, *parts[1:]]
    proc = await asyncio.create_subprocess_exec(
        *exec_parts,
        cwd=cwd,
        env=safe_subprocess_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
        preexec_fn=preexec_fn,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        await terminate_process_tree(proc)
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
            "默认受设置中的 terminal 开关、白名单与禁止项约束，"
            "并应用资源限制与超时进程组回收；"
            "不用于文件读写/搜索（优先 read_file 与 search_files）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "timeout": {"type": "number", "minimum": 0.1, "default": DEFAULT_TIMEOUT},
                "workdir": {"type": "string", "description": "可选工作目录（默认 workspace 根目录）"},
            },
            "required": ["command"],
        },
        handler=_terminal,
        enabled=True,
        category="builtin",
    )
)
