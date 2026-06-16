"""subprocess_env 与 env_vars 按名解析测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.db import init_db
from agentpod_agent.env_vars import add_env_var, resolve_env_var_names
from agentpod_agent.subprocess_env import (
    is_reserved_env_name,
    merge_subprocess_env,
    normalize_env_names,
    safe_subprocess_env,
)
from agentpod_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()


def test_normalize_env_names_dedupes_and_skips_empty() -> None:
    assert normalize_env_names(["GITHUB_TOKEN", "  ", "GITHUB_TOKEN", "SMTP_PASSWORD"]) == [
        "GITHUB_TOKEN",
        "SMTP_PASSWORD",
    ]
    assert normalize_env_names(None) == []
    assert normalize_env_names("GITHUB_TOKEN") == []


def test_merge_subprocess_env_overlays_workspace_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/tmp/home")
    merged = merge_subprocess_env(workspace_vars={"GITHUB_TOKEN": "gh_secret"})
    assert merged["PATH"] == "/usr/bin"
    assert merged["GITHUB_TOKEN"] == "gh_secret"
    assert "INTERNAL_TOKEN" not in merged


def test_safe_subprocess_env_whitelist_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("INTERNAL_TOKEN", "must-not-leak")
    env = safe_subprocess_env()
    assert env.get("PATH") == "/bin"
    assert "INTERNAL_TOKEN" not in env


@pytest.mark.asyncio
async def test_resolve_env_var_names_returns_values_in_order() -> None:
    await add_env_var("ALPHA", "a", "")
    await add_env_var("BETA", "b", "")
    resolved = await resolve_env_var_names(["BETA", "ALPHA"])
    assert resolved == {"BETA": "b", "ALPHA": "a"}


@pytest.mark.asyncio
async def test_resolve_env_var_names_raises_on_missing() -> None:
    await add_env_var("KNOWN", "v", "")
    with pytest.raises(ValueError, match="env var not found: MISSING"):
        await resolve_env_var_names(["KNOWN", "MISSING"])


@pytest.mark.asyncio
async def test_resolve_env_var_names_normalizes_input() -> None:
    await add_env_var("TOKEN", "secret", "")
    resolved = await resolve_env_var_names([" TOKEN ", "TOKEN"])
    assert resolved == {"TOKEN": "secret"}


def test_is_reserved_env_name_blocks_system_keys() -> None:
    assert is_reserved_env_name("PATH")
    assert is_reserved_env_name("path")
    assert is_reserved_env_name("INTERNAL_TOKEN")
    assert is_reserved_env_name("AGENTPOD_HOME")
    assert not is_reserved_env_name("GITHUB_TOKEN")


def test_merge_subprocess_env_ignores_reserved_workspace_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    merged = merge_subprocess_env(workspace_vars={"GITHUB_TOKEN": "gh", "PATH": "/evil"})
    assert merged["GITHUB_TOKEN"] == "gh"
    assert merged["PATH"] == "/usr/bin"


@pytest.mark.asyncio
async def test_resolve_env_var_names_rejects_reserved() -> None:
    with pytest.raises(ValueError, match="env var name not allowed: PATH"):
        await resolve_env_var_names(["PATH"])


@pytest.mark.asyncio
async def test_add_env_var_rejects_reserved_name() -> None:
    with pytest.raises(ValueError, match="reserved env var name"):
        await add_env_var("PATH", "/evil", "")
