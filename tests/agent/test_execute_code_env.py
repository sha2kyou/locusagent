"""execute_code / proc_env 环境变量注入测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from locus_agent.db import init_db
from locus_agent.env_vars import add_env_var
from locus_agent.tools.base import ToolError
from locus_agent.tools.execute_code import _execute_code
from locus_agent.tools.proc_env import build_proc_env
from locus_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_workspace_id(WS_TEST)
    init_db()
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr("locus_agent.tools.execute_code.workspace_root_dir", lambda: root)
    monkeypatch.setattr(
        "locus_agent.tools.execute_code.resolve_workdir",
        lambda workdir, restrict_to_workspace=True: root,
    )
    monkeypatch.setattr("locus_agent.tools.execute_code.build_sandbox_preexec_fn", lambda: None)


@pytest.mark.asyncio
async def test_build_proc_env_injects_workspace_vars() -> None:
    await add_env_var("GITHUB_TOKEN", "gh_secret", "")
    env = await build_proc_env({"env": ["GITHUB_TOKEN"]})
    assert env["GITHUB_TOKEN"] == "gh_secret"
    assert "INTERNAL_TOKEN" not in env


@pytest.mark.asyncio
async def test_build_proc_env_rejects_missing() -> None:
    with pytest.raises(ToolError, match="env var not found"):
        await build_proc_env({"env": ["MISSING"]})


@pytest.mark.asyncio
async def test_build_proc_env_rejects_reserved() -> None:
    with pytest.raises(ToolError, match="env var name not allowed"):
        await build_proc_env({"env": ["PATH"]})


@pytest.mark.asyncio
async def test_execute_code_passes_env_to_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    await add_env_var("MY_TOKEN", "tok123", "")
    captured: dict[str, object] = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self, _stdin: bytes | None = None) -> tuple[bytes, bytes]:
            return b"ok", b""

    async def _fake_exec(*_cmd: object, **kwargs: object) -> _FakeProc:
        captured.update(kwargs)
        return _FakeProc()

    async def _fake_python() -> str:
        return "python3"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("locus_agent.tools.execute_code._workspace_python", _fake_python)

    result = await _execute_code(
        {
            "code": "import os; print(os.environ['MY_TOKEN'])",
            "env": ["MY_TOKEN"],
        }
    )
    assert result.metadata["exit_code"] == 0
    assert captured["env"]["MY_TOKEN"] == "tok123"
