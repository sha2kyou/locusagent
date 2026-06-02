"""API Key 生成与校验测试。"""

from __future__ import annotations

import os

import pytest

from agentpod_host.security.api_key import (
    API_KEY_PREFIX,
    generate_agent_api_key,
    hash_agent_api_key,
    verify_agent_api_key,
)


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    from agentpod_host.config import get_settings

    get_settings.cache_clear()


def test_generate_agent_api_key_uses_apod_prefix():
    key = generate_agent_api_key()
    assert key.startswith(API_KEY_PREFIX)
    assert "gwzz_" not in key


def test_verify_agent_api_key_roundtrip():
    key = generate_agent_api_key()
    hashed = hash_agent_api_key(key)
    assert verify_agent_api_key(key, hashed)
    assert not verify_agent_api_key(key + "x", hashed)
