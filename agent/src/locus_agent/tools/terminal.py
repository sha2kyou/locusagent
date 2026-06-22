"""terminal 工具：执行 shell 命令（受开关与白名单约束）。"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from pathlib import Path
from typing import Any

from locus_shared.workspace_venv import WorkspaceVenvError, ensure_workspace_venv, workspace_venv_pip

from ..config import get_settings
from ..subprocess_sandbox import (
    build_sandbox_preexec_fn,
    resolve_workdir,
    should_restrict_terminal_workdir,
    terminate_process_tree,
)
from ..workspace import get_workspace_id
from .proc_env import build_proc_env
from ..subprocess_env import safe_subprocess_env
from .base import Tool, ToolError, ToolResult, register_builtin

DEFAULT_TIMEOUT = 180.0
MAX_OUTPUT = 100 * 1024

_WORKSPACE_PYTHON_CMDS = frozenset({"python", "python3"})
_WORKSPACE_PIP_CMDS = frozenset({"pip", "pip3"})


def _command_set(raw: str) -> set[str]:
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _enabled() -> bool:
    return get_settings().enable_terminal


def _whitelist() -> set[str]:
    return _command_set(get_settings().terminal_whitelist)


def _denylist() -> set[str]:
    return _command_set(get_settings().terminal_denylist)


async def _resolve_executable(head: str) -> str:
    wid = get_workspace_id()
    if head in _WORKSPACE_PYTHON_CMDS:
        try:
            py = await asyncio.to_thread(ensure_workspace_venv, wid)
        except WorkspaceVenvError as exc:
            raise ToolError(str(exc)) from exc
        return str(py)
    if head in _WORKSPACE_PIP_CMDS:
        try:
            await asyncio.to_thread(ensure_workspace_venv, wid)
        except WorkspaceVenvError as exc:
            raise ToolError(str(exc)) from exc
        pip = workspace_venv_pip(wid)
        if not pip.is_file():
            raise ToolError("pip not found in workspace virtualenv")
        return str(pip)
    resolved = shutil.which(head, path=safe_subprocess_env().get("PATH"))
    if not resolved:
        raise ToolError(f"command '{head}' not found in PATH")
    exec_name = Path(resolved).name.lower()
    if exec_name != head:
        raise ToolError(f"resolved executable mismatch for command '{head}'")
    return resolved


async def _terminal(args: dict[str, Any]) -> ToolResult:
    if not _enabled():
        raise ToolError("terminal disabled; enable it in Settings → Tools")
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
        raise ToolError("terminal allowlist is empty; configure allowed commands in Settings → Tools")
    if head not in wl:
        raise ToolError(f"command '{head}' not in whitelist")
    if head in _denylist():
        raise ToolError(f"command '{head}' is blocked by TERMINAL_DENYLIST")
    resolved = await _resolve_executable(head)
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
    proc_env = await build_proc_env(args)
    proc = await asyncio.create_subprocess_exec(
        *exec_parts,
        cwd=cwd,
        env=proc_env,
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
            "Run shell commands for build, install, git, process management, scripts. "
            "python/pip commands use the current workspace virtualenv (workspace/.venv). "
            "Subject to terminal enable flag, allow/deny lists, resource limits, timeout cleanup; "
            "not for file read/search (prefer read_file and search_files). "
            "Optional env: workspace env var names to inject (values from env_vars store)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "number", "minimum": 0.1, "default": DEFAULT_TIMEOUT},
                "workdir": {"type": "string", "description": "Optional working directory (default workspace root)"},
                "env": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workspace env var names to inject into the process environment.",
                },
            },
            "required": ["command"],
        },
        handler=_terminal,
        enabled=True,
        category="builtin",
    )
)
