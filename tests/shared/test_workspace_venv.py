"""Per-workspace virtualenv helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from locus_shared.workspace_venv import (
    ensure_workspace_venv,
    is_workspace_venv_ready,
    workspace_files_root,
    workspace_venv_dir,
    workspace_venv_python,
    with_workspace_venv_path,
)

WS = "ws_0123456789abcdef0123"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "locusagent-home"
    monkeypatch.setenv("LOCUSAGENT_HOME", str(root))
    return root


def test_workspace_venv_paths(home: Path) -> None:
    assert workspace_files_root(WS, home=home) == home / "workspaces" / WS / "workspace"
    assert workspace_venv_dir(WS, home=home) == home / "workspaces" / WS / "workspace" / ".venv"


def test_ensure_workspace_venv_creates_python(home: Path) -> None:
    assert not is_workspace_venv_ready(WS, home=home)
    py = ensure_workspace_venv(WS, home=home)
    assert py == workspace_venv_python(WS, home=home)
    assert py.is_file()
    assert is_workspace_venv_ready(WS, home=home)


def test_ensure_workspace_venv_idempotent(home: Path) -> None:
    first = ensure_workspace_venv(WS, home=home)
    second = ensure_workspace_venv(WS, home=home)
    assert first == second


def test_with_workspace_venv_path_prepends_bin(home: Path) -> None:
    ensure_workspace_venv(WS, home=home)
    env = with_workspace_venv_path({"PATH": "/usr/bin"}, WS, home=home)
    bin_dir = str(workspace_venv_python(WS, home=home).parent)
    assert env["PATH"].startswith(bin_dir)
    assert "/usr/bin" in env["PATH"]
