"""execute_code 工具：受控执行代码（当前支持 Python）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from locus_shared.workspace_venv import WorkspaceVenvError, ensure_workspace_venv

from ..subprocess_sandbox import (
    build_sandbox_preexec_fn,
    resolve_workdir,
    terminate_process_tree,
    workspace_root_dir,
)
from ..workspace import get_workspace_id
from .proc_env import build_proc_env
from .base import Tool, ToolError, ToolResult, register_builtin

DEFAULT_TIMEOUT = 30.0
MAX_OUTPUT = 100 * 1024


def _workspace_root() -> Path:
    return workspace_root_dir()


def _resolve_workdir(workdir: str | None) -> Path:
    try:
        return resolve_workdir(workdir, restrict_to_workspace=True)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


async def _workspace_python() -> str:
    wid = get_workspace_id()
    try:
        py = await asyncio.to_thread(ensure_workspace_venv, wid)
    except WorkspaceVenvError as exc:
        raise ToolError(str(exc)) from exc
    return str(py)


async def _execute_code(args: dict[str, Any]) -> ToolResult:
    language = str(args.get("language", "python") or "python").strip().lower()
    if language not in {"python", "py"}:
        raise ToolError("only python is supported for now")
    code = str(args.get("code", "") or "")
    if not code.strip():
        raise ToolError("code is required")
    timeout = float(args.get("timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)
    if timeout <= 0:
        raise ToolError("timeout must be > 0")
    stdin_text = str(args.get("stdin", "") or "")

    root = _workspace_root()
    cwd = _resolve_workdir(str(args.get("workdir", "") or "").strip() or None)
    py = await _workspace_python()
    preexec_fn = build_sandbox_preexec_fn()
    proc_env = await build_proc_env(args)

    proc = await asyncio.create_subprocess_exec(
        py,
        "-c",
        code,
        cwd=str(cwd),
        env=proc_env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        preexec_fn=preexec_fn,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin_text.encode("utf-8")), timeout=timeout)
    except TimeoutError:
        await terminate_process_tree(proc)
        raise ToolError(f"execution timed out after {timeout}s") from None

    stdout = (out or b"").decode("utf-8", errors="replace")
    stderr = (err or b"").decode("utf-8", errors="replace")
    merged = f"exit={proc.returncode}\n[stdout]\n{stdout}\n[stderr]\n{stderr}"
    if len(merged) > MAX_OUTPUT:
        merged = merged[:MAX_OUTPUT] + "\n...(output truncated)"
    return ToolResult(
        content=merged,
        metadata={"exit_code": proc.returncode, "workdir": str(cwd.relative_to(root)) or "."},
    )


register_builtin(
    Tool(
        name="execute_code",
        description=(
            "Run a code snippet (Python). Uses the current workspace virtualenv "
            "(workspace/.venv; created on workspace setup or first run). "
            "Subject to resource limits and timeout process-group cleanup. "
            "Optional env: workspace env var names to inject (values resolved from env_vars store; "
            "use os.environ in code—do not embed secrets in code)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["python"], "default": "python"},
                "code": {"type": "string", "description": "Code to execute"},
                "stdin": {"type": "string", "description": "Optional stdin"},
                "timeout": {"type": "number", "minimum": 0.1, "default": DEFAULT_TIMEOUT},
                "workdir": {"type": "string", "description": "Optional path relative to workspace"},
                "env": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workspace env var names to inject into the process environment.",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        handler=_execute_code,
    )
)

