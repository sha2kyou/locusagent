"""execute_code 工具：受控执行代码（当前支持 Python）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..subprocess_sandbox import (
    build_sandbox_preexec_fn,
    resolve_workdir,
    terminate_process_tree,
    workspace_root_dir,
)
from ..subprocess_env import safe_subprocess_env
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


def _python_bin(root: Path) -> str:
    venv_py = root / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.is_file() else "python3"


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
    py = _python_bin(root)
    preexec_fn = build_sandbox_preexec_fn()

    proc = await asyncio.create_subprocess_exec(
        py,
        "-c",
        code,
        cwd=str(cwd),
        env=safe_subprocess_env(),
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
            "执行代码片段（当前支持 Python）。默认在 workspace 下运行；若存在 .venv，优先使用 .venv/bin/python。"
            "执行进程受资源限制与超时进程组回收约束。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["python"], "default": "python"},
                "code": {"type": "string", "description": "要执行的代码"},
                "stdin": {"type": "string", "description": "可选标准输入"},
                "timeout": {"type": "number", "minimum": 0.1, "default": DEFAULT_TIMEOUT},
                "workdir": {"type": "string", "description": "可选相对 workspace 的工作目录"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        handler=_execute_code,
    )
)

