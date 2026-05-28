"""agent_api_key 生成与哈希校验。

生成：`apod_` 前缀 + 43 字符 token_urlsafe(32)。
存储：sha256(SESSION_SECRET || api_key) 的 hex；明文仅生成时返回一次。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..config import get_settings

API_KEY_PREFIX = "apod_"
LEGACY_API_KEY_PREFIX = "gwzz_"


def generate_agent_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_agent_api_key(api_key: str) -> str:
    settings = get_settings()
    salt = settings.session_secret.encode("utf-8") or b"agentpod-default-salt"
    digest = hashlib.sha256()
    digest.update(salt)
    digest.update(api_key.encode("utf-8"))
    return digest.hexdigest()


def verify_agent_api_key(api_key: str, expected_hash: str) -> bool:
    if not api_key or not expected_hash:
        return False
    return hmac.compare_digest(hash_agent_api_key(api_key), expected_hash)
