"""终端命令确认与白名单持久化测试。"""

from __future__ import annotations

import asyncio
import time

import pytest

from locus_agent.config import get_settings
from locus_agent.core.run_context import (
    reset_chat_session_id,
    reset_run_event_emitter,
    set_chat_session_id,
    set_run_event_emitter,
)
from locus_agent.tools.base import ToolError
from locus_agent.tools.terminal_approval import (
    classify_terminal_head,
    deny_pending_for_session,
    list_pending_terminal_approvals,
    request_terminal_command_approval,
    resolve_terminal_approval,
)
from locus_shared.settings_store import (
    append_terminal_denylist_command,
    append_terminal_whitelist_command,
    clear_settings_cache,
    load_settings_document,
    save_settings_document,
)


@pytest.fixture(autouse=True)
def _reset_settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCUSAGENT_HOME", str(tmp_path))
    clear_settings_cache()
    get_settings.cache_clear()
    doc = load_settings_document()
    doc.terminal.whitelist = "git,npm"
    doc.terminal.denylist = "bash,sh"
    save_settings_document(doc)
    clear_settings_cache()
    get_settings.cache_clear()
    yield
    clear_settings_cache()
    get_settings.cache_clear()


def test_classify_terminal_head() -> None:
    assert classify_terminal_head("git") == "allow"
    assert classify_terminal_head("bash") == "deny"
    assert classify_terminal_head("curl") == "confirm"


def test_append_terminal_whitelist_removes_from_denylist() -> None:
    append_terminal_whitelist_command("curl")
    doc = load_settings_document()
    assert "curl" in doc.terminal.whitelist
    assert "curl" not in doc.terminal.denylist


def test_append_terminal_denylist_removes_from_whitelist() -> None:
    append_terminal_denylist_command("git")
    doc = load_settings_document()
    assert "git" in doc.terminal.denylist
    assert "git" not in doc.terminal.whitelist


@pytest.mark.asyncio
async def test_request_terminal_command_approval_once() -> None:
    emitted: list[dict] = []

    async def _emit(ev: dict) -> None:
        emitted.append(ev)

    session_token = set_chat_session_id("sess_1")
    emitter_token = set_run_event_emitter(_emit)
    try:

        async def _approve_later() -> None:
            await asyncio.sleep(0.05)
            approval_id = emitted[0]["approval_id"]
            await resolve_terminal_approval(approval_id, choice="once", session_id="sess_1")

        task = asyncio.create_task(_approve_later())
        await request_terminal_command_approval(
            command="curl https://example.com",
            head="curl",
            tool_call_id="call_test_1",
        )
        await task
    finally:
        reset_run_event_emitter(emitter_token)
        reset_chat_session_id(session_token)

    assert emitted[0]["type"] == "terminal_approval"
    assert emitted[0]["head"] == "curl"
    assert emitted[0]["tool_call_id"] == "call_test_1"
    assert emitted[0]["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_request_terminal_command_approval_non_interactive_immediate_deny() -> None:
    session_token = set_chat_session_id("sess_noninteractive")
    try:
        with pytest.raises(ToolError, match="non-interactive runs"):
            await request_terminal_command_approval(command="wget test", head="wget")
    finally:
        reset_chat_session_id(session_token)


@pytest.mark.asyncio
async def test_request_terminal_command_approval_timeout_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("locus_agent.tools.terminal_approval.TERMINAL_APPROVAL_TIMEOUT_S", 0.2)

    async def _emit(_ev: dict) -> None:
        return None

    session_token = set_chat_session_id("sess_timeout")
    emitter_token = set_run_event_emitter(_emit)
    try:
        with pytest.raises(ToolError, match="denied by user"):
            await request_terminal_command_approval(command="wget -qO- test", head="wget")
    finally:
        reset_run_event_emitter(emitter_token)
        reset_chat_session_id(session_token)


@pytest.mark.asyncio
async def test_deny_pending_for_session_unblocks_wait() -> None:
    async def _emit(_ev: dict) -> None:
        return None

    session_token = set_chat_session_id("sess_cancel")
    emitter_token = set_run_event_emitter(_emit)
    try:

        async def _wait() -> None:
            with pytest.raises(ToolError, match="denied by user"):
                await request_terminal_command_approval(command="wget test", head="wget")

        task = asyncio.create_task(_wait())
        await asyncio.sleep(0.05)
        assert await deny_pending_for_session("sess_cancel") == 1
        await task
    finally:
        reset_run_event_emitter(emitter_token)
        reset_chat_session_id(session_token)


@pytest.mark.asyncio
async def test_list_pending_includes_expires_at() -> None:
    async def _emit(_ev: dict) -> None:
        return None

    session_token = set_chat_session_id("sess_list")
    emitter_token = set_run_event_emitter(_emit)

    async def _hold() -> None:
        with pytest.raises(ToolError):
            await request_terminal_command_approval(
                command="curl test",
                head="curl",
                tool_call_id="call_list_1",
            )

    task = asyncio.create_task(_hold())
    await asyncio.sleep(0.05)
    try:
        items = await list_pending_terminal_approvals("sess_list")
        assert len(items) == 1
        assert items[0]["tool_call_id"] == "call_list_1"
        assert items[0]["expires_at"] > time.time()
    finally:
        await deny_pending_for_session("sess_list")
        await task
        reset_run_event_emitter(emitter_token)
        reset_chat_session_id(session_token)
