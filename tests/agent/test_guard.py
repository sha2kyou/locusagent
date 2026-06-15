"""写入安全门测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agentpod_agent.security.guard import review_write


def _guard_enabled_settings():
    return SimpleNamespace(write_guard_enabled=True)


@pytest.mark.asyncio
async def test_review_write_skipped_when_guard_disabled():
    with patch("agentpod_agent.security.guard.get_settings", return_value=SimpleNamespace(write_guard_enabled=False)):
        result = await review_write("-----BEGIN RSA PRIVATE KEY-----\nabc", kind="memory")
    assert result.allowed
    assert result.reason == "guard disabled"


@pytest.mark.asyncio
async def test_review_write_blocks_hard_secret():
    with patch("agentpod_agent.security.guard.get_settings", return_value=_guard_enabled_settings()):
        result = await review_write("-----BEGIN RSA PRIVATE KEY-----\nabc", kind="memory")
    assert not result.allowed
    assert "私钥" in result.reason


@pytest.mark.asyncio
async def test_review_write_fail_closed_on_llm_error():
    with patch("agentpod_agent.security.guard.get_settings", return_value=_guard_enabled_settings()):
        with patch("agentpod_agent.core.auxiliary_completion.create_chat_completion", new=AsyncMock(side_effect=RuntimeError("down"))):
            with patch("agentpod_agent.core.models.resolve_model", new=AsyncMock(return_value="gpt-test")):
                result = await review_write("safe preference text", kind="memory")
    assert not result.allowed
    assert "blocked" in result.reason


@pytest.mark.asyncio
async def test_review_write_fail_closed_on_empty_review():
    mock_resp = type("Resp", (), {"usage": None})()
    with patch("agentpod_agent.security.guard.get_settings", return_value=_guard_enabled_settings()):
        with patch("agentpod_agent.core.auxiliary_completion.create_chat_completion", new=AsyncMock(return_value=mock_resp)):
            with patch("agentpod_agent.core.models.resolve_model", new=AsyncMock(return_value="gpt-test")):
                with patch("agentpod_agent.core.openai_fields.openai_completion_text", return_value=""):
                    result = await review_write("safe preference text", kind="memory")
    assert not result.allowed


@pytest.mark.asyncio
async def test_review_write_fail_closed_on_invalid_json():
    mock_resp = type("Resp", (), {"usage": None})()
    with patch("agentpod_agent.security.guard.get_settings", return_value=_guard_enabled_settings()):
        with patch("agentpod_agent.core.auxiliary_completion.create_chat_completion", new=AsyncMock(return_value=mock_resp)):
            with patch("agentpod_agent.core.models.resolve_model", new=AsyncMock(return_value="gpt-test")):
                with patch("agentpod_agent.core.openai_fields.openai_completion_text", return_value="not-json"):
                    result = await review_write("safe preference text", kind="memory")
    assert not result.allowed


@pytest.mark.asyncio
async def test_review_write_allows_when_llm_approves():
    mock_resp = type("Resp", (), {"usage": None})()
    with patch("agentpod_agent.security.guard.get_settings", return_value=_guard_enabled_settings()):
        with patch("agentpod_agent.core.auxiliary_completion.create_chat_completion", new=AsyncMock(return_value=mock_resp)):
            with patch("agentpod_agent.core.models.resolve_model", new=AsyncMock(return_value="gpt-test")):
                with patch("agentpod_agent.core.openai_fields.openai_completion_text", return_value='{"allow": true, "reason": "ok"}'):
                    with patch("agentpod_agent.usage_report.schedule_openai_usage"):
                        result = await review_write("User prefers concise answers.", kind="memory")
    assert result.allowed
