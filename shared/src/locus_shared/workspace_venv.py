"""Per-workspace Python virtualenv under workspace/.venv."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from locus_shared.paths import locusagent_home
from locus_shared.workspace_ids import normalize_workspace_id


class WorkspaceVenvError(RuntimeError):
    """Failed to create or use a workspace virtual environment."""


def workspace_files_root(workspace_id: str, *, home: Path | None = None) -> Path:
    wid = normalize_workspace_id(workspace_id)
    base = home if home is not None else locusagent_home()
    return base / "workspaces" / wid / "workspace"


def workspace_venv_dir(workspace_id: str, *, home: Path | None = None) -> Path:
    return workspace_files_root(workspace_id, home=home) / ".venv"


def _venv_scripts_dir(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts"
    return venv_dir / "bin"


def _venv_python_candidates(scripts: Path) -> tuple[Path, ...]:
    if sys.platform == "win32":
        return (scripts / "python.exe", scripts / "python3.exe")
    return (scripts / "python", scripts / "python3")


def _resolve_workspace_venv_python(venv_dir: Path) -> Path:
    scripts = _venv_scripts_dir(venv_dir)
    for candidate in _venv_python_candidates(scripts):
        if candidate.is_file():
            return candidate
    return _venv_python_candidates(scripts)[-1]


def workspace_venv_python(workspace_id: str, *, home: Path | None = None) -> Path:
    return _resolve_workspace_venv_python(workspace_venv_dir(workspace_id, home=home))


def workspace_venv_pip(workspace_id: str, *, home: Path | None = None) -> Path:
    scripts = _venv_scripts_dir(workspace_venv_dir(workspace_id, home=home))
    if sys.platform == "win32":
        return scripts / "pip.exe"
    pip = scripts / "pip"
    if pip.is_file():
        return pip
    return scripts / "pip3"


def is_workspace_venv_ready(workspace_id: str, *, home: Path | None = None) -> bool:
    return workspace_venv_python(workspace_id, home=home).is_file()


def with_workspace_venv_path(env: dict[str, str], workspace_id: str, *, home: Path | None = None) -> dict[str, str]:
    if not is_workspace_venv_ready(workspace_id, home=home):
        return env
    bin_dir = str(_venv_scripts_dir(workspace_venv_dir(workspace_id, home=home)))
    out = dict(env)
    path = out.get("PATH", "")
    out["PATH"] = f"{bin_dir}{os.pathsep}{path}" if path else bin_dir
    return out


def ensure_workspace_venv(workspace_id: str, *, home: Path | None = None) -> Path:
    """Create workspace/.venv if missing; return path to venv python."""
    venv_dir = workspace_venv_dir(workspace_id, home=home)
    py = workspace_venv_python(workspace_id, home=home)
    if py.is_file():
        return py
    root = workspace_files_root(workspace_id, home=home)
    root.mkdir(parents=True, exist_ok=True)

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise WorkspaceVenvError(f"failed to create workspace venv: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise WorkspaceVenvError(
            f"failed to create workspace venv (exit {completed.returncode})"
            + (f": {detail}" if detail else "")
        )

    py = _resolve_workspace_venv_python(venv_dir)
    if not py.is_file():
        raise WorkspaceVenvError(f"workspace venv created but python missing: {py}")
    return py
