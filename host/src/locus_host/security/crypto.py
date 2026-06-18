"""对称加密：基于 Fernet（AES-128-CBC + HMAC-SHA256）。

ENCRYPTION_KEY 期望为 base64-urlsafe 编码的 32 字节随机值。
不复用作 SESSION_SECRET，二者职责互斥。
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.encryption_key
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY 未配置")
    try:
        key_bytes = base64.urlsafe_b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("ENCRYPTION_KEY 必须为 base64-urlsafe 编码") from exc
    if len(key_bytes) != 32:
        derived = hashlib.sha256(raw.encode("utf-8")).digest()
        key_bytes = derived
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_bytes(plaintext: bytes) -> bytes:
    return _fernet().encrypt(plaintext)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise RuntimeError("解密失败：token 无效或密钥不匹配") from exc


def encrypt_str(plaintext: str) -> bytes:
    return encrypt_bytes(plaintext.encode("utf-8"))


def decrypt_str(token: bytes) -> str:
    return decrypt_bytes(token).decode("utf-8")
