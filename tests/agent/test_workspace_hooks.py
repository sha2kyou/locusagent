"""工作区 hook 加载与 hook_manage 工具测试。"""

from __future__ import annotations

import time

import pytest

from agentpod_agent.db import init_db
from agentpod_agent.hooks import clear_hooks, emit_post_user_submit, list_post_user_submit_hooks, register_post_user_submit
from agentpod_agent.hooks.loader import reload_workspace_hooks
from agentpod_agent.hooks.store import create_hook, delete_hook, list_hooks
from agentpod_agent.tool_settings import set_hook_enabled
from agentpod_agent.tools.agent_hooks import _hook_manage, _hook_view
from agentpod_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()
    clear_hooks()
    from agentpod_agent.hooks.loader import _unload_loaded_modules

    for name in list(list_hooks()):
        delete_hook(name)
    clear_hooks()
    _unload_loaded_modules()
    yield
    clear_hooks()
    _unload_loaded_modules()


def _hook_body() -> str:
    return '''
seen = []

def on_user_submit(*, hook_name, user_message, **kwargs):
    seen.append((hook_name, user_message))

def register(ctx):
    ctx.register_post_user_submit(on_user_submit)
'''.strip() + "\n"


@pytest.mark.asyncio
async def test_hook_manage_create_and_reload() -> None:
    result = await _hook_manage({"action": "create", "name": "demo-hook", "body": _hook_body()})
    assert "created" in result.content
    stats = reload_workspace_hooks()
    assert stats.hooks_loaded == 1
    assert stats.callbacks_registered == 1
    entries = list_post_user_submit_hooks()
    assert entries[0]["hook_name"] == "demo-hook"

    await emit_post_user_submit(session_id="sess-1", user_message="hello", submit_source="chat")

    import sys

    mod = sys.modules[[k for k in sys.modules if k.startswith("agentpod_hook_demo_hook_")][0]]
    assert mod.seen == [("demo-hook", "hello")]


@pytest.mark.asyncio
async def test_hook_view_lists_hooks() -> None:
    await _hook_manage({"action": "create", "name": "list-hook", "body": _hook_body()})
    result = await _hook_view({})
    assert "list-hook" in result.content
    assert "loaded" in result.content


@pytest.mark.asyncio
async def test_hook_manage_delete_unloads() -> None:
    await _hook_manage({"action": "create", "name": "gone-hook", "body": _hook_body()})
    assert reload_workspace_hooks().callbacks_registered == 1
    await _hook_manage({"action": "delete", "name": "gone-hook"})
    assert list_hooks() == []
    assert list_post_user_submit_hooks() == []


def test_create_hook_uses_default_template() -> None:
    create_hook("template-hook")
    stats = reload_workspace_hooks()
    assert stats.hooks_loaded == 1


@pytest.mark.asyncio
async def test_disabled_hook_not_loaded() -> None:
    await _hook_manage({"action": "create", "name": "off-hook", "body": _hook_body()})
    assert reload_workspace_hooks().callbacks_registered == 1
    set_hook_enabled("off-hook", False)
    assert reload_workspace_hooks().callbacks_registered == 0


@pytest.mark.asyncio
async def test_hook_callback_timeout_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentpod_agent import config as config_mod

    settings = config_mod.get_settings()
    monkeypatch.setattr(settings, "hook_callback_timeout_seconds", 0.2)

    def slow(**kwargs: object) -> None:
        time.sleep(1.0)

    register_post_user_submit(slow)
    started = time.monotonic()
    await emit_post_user_submit(session_id="sess-timeout", user_message="x", submit_source="chat")
    elapsed = time.monotonic() - started
    assert elapsed < 0.9


@pytest.mark.asyncio
async def test_emit_passes_submit_source_and_legacy_source_alias() -> None:
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> None:
        captured.update(kwargs)

    register_post_user_submit(capture)
    await emit_post_user_submit(session_id="s", user_message="hi", submit_source="scheduled")
    assert captured["submit_source"] == "scheduled"
    assert captured["source"] == "scheduled"
