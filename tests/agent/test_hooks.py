"""post_user_submit hook 测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.hooks import (
    clear_hooks,
    emit_post_user_submit,
    register_post_user_submit,
)


@pytest.fixture(autouse=True)
def _reset_hooks() -> None:
    clear_hooks()
    yield
    clear_hooks()


@pytest.mark.asyncio
async def test_post_user_submit_invokes_sync_callback() -> None:
    seen: list[dict[str, object]] = []

    def on_submit(**kwargs: object) -> None:
        seen.append(dict(kwargs))

    register_post_user_submit(on_submit)
    await emit_post_user_submit(
        session_id="sess-1",
        user_message="hello",
        user_message_id=42,
        submit_source="chat",
    )

    assert len(seen) == 1
    assert seen[0]["session_id"] == "sess-1"
    assert seen[0]["user_message"] == "hello"
    assert seen[0]["user_message_id"] == 42
    assert seen[0]["submit_source"] == "chat"
    assert seen[0]["source"] == "chat"
    assert seen[0]["is_regenerate"] is False
    assert seen[0]["attachment_ids"] == []


@pytest.mark.asyncio
async def test_post_user_submit_invokes_async_callback() -> None:
    seen: list[str] = []

    async def on_submit(*, user_message: str, **kwargs: object) -> None:
        seen.append(user_message)

    register_post_user_submit(on_submit)
    await emit_post_user_submit(session_id="sess-2", user_message="async")

    assert seen == ["async"]


@pytest.mark.asyncio
async def test_post_user_submit_callback_error_does_not_break() -> None:
    calls = {"ok": 0}

    def boom(**kwargs: object) -> None:
        raise RuntimeError("hook failed")

    def ok(**kwargs: object) -> None:
        calls["ok"] += 1

    register_post_user_submit(boom)
    register_post_user_submit(ok)
    await emit_post_user_submit(session_id="sess-3", user_message="x")

    assert calls["ok"] == 1
