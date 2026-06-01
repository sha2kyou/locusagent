"""Subprocess sandbox helpers for tool execution."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Callable

from .workspace import workspace_data_dir

_DEFAULT_MEMORY_MB = 512
_DEFAULT_CPU_SECONDS = 20
_DEFAULT_MAX_PROCS = 64
_DEFAULT_MAX_OPEN_FILES = 256
_DEFAULT_MAX_FILE_MB = 16
_DEFAULT_KILL_GRACE_SECONDS = 2.0


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, *, minimum: float = 0.1) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def workspace_root_dir() -> Path:
    root = workspace_data_dir() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_workdir(
    workdir: str | None,
    *,
    restrict_to_workspace: bool,
) -> Path:
    root = workspace_root_dir().resolve()
    if not workdir:
        return root
    raw = str(workdir).strip()
    if not raw:
        return root
    if os.path.isabs(raw):
        candidate = Path(raw).resolve()
        if restrict_to_workspace:
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"workdir escapes workspace: {raw}") from exc
    else:
        candidate = (root / raw).resolve()
        if restrict_to_workspace:
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"workdir escapes workspace: {raw}") from exc
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(f"workdir not found: {raw}")
    return candidate


def should_restrict_terminal_workdir() -> bool:
    return _env_bool("TERMINAL_RESTRICT_WORKSPACE", True)


def sandbox_kill_grace_seconds() -> float:
    return _env_float("SANDBOX_KILL_GRACE_SECONDS", _DEFAULT_KILL_GRACE_SECONDS)


def sandbox_limits_from_env() -> dict[str, int]:
    return {
        "memory_mb": _env_int("SANDBOX_MAX_MEMORY_MB", _DEFAULT_MEMORY_MB),
        "cpu_seconds": _env_int("SANDBOX_MAX_CPU_SECONDS", _DEFAULT_CPU_SECONDS),
        "max_procs": _env_int("SANDBOX_MAX_PROCESSES", _DEFAULT_MAX_PROCS),
        "max_open_files": _env_int("SANDBOX_MAX_OPEN_FILES", _DEFAULT_MAX_OPEN_FILES),
        "max_file_mb": _env_int("SANDBOX_MAX_FILE_MB", _DEFAULT_MAX_FILE_MB),
    }


def build_sandbox_preexec_fn() -> Callable[[], None] | None:
    if os.name != "posix":
        return None

    limits = sandbox_limits_from_env()

    def _apply_limits() -> None:
        import resource

        file_bytes = limits["max_file_mb"] * 1024 * 1024
        memory_bytes = limits["memory_mb"] * 1024 * 1024
        rules: list[tuple[int, int, int]] = [
            (resource.RLIMIT_CPU, limits["cpu_seconds"], limits["cpu_seconds"]),
            (resource.RLIMIT_NOFILE, limits["max_open_files"], limits["max_open_files"]),
            (resource.RLIMIT_FSIZE, file_bytes, file_bytes),
            (resource.RLIMIT_NPROC, limits["max_procs"], limits["max_procs"]),
        ]
        if hasattr(resource, "RLIMIT_AS"):
            rules.append((resource.RLIMIT_AS, memory_bytes, memory_bytes))
        for limit_name, soft, hard in rules:
            try:
                resource.setrlimit(limit_name, (soft, hard))
            except Exception:
                # Best-effort limits: keep tool available even if one rule cannot apply.
                continue

    return _apply_limits


async def terminate_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    grace_seconds = sandbox_kill_grace_seconds()
    try:
        if proc.pid:
            os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass
    try:
        if proc.pid:
            os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception:
        proc.kill()
    await proc.wait()
