"""附件存储配置校验。"""

from __future__ import annotations

from ..config import Settings, get_settings

_WEAK_S3_PAIRS = frozenset(
    {
        ("agentpod", "agentpodsecret"),
        ("minioadmin", "minioadmin"),
    }
)


def validate_attachment_storage(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    if s.attachment_storage.strip().lower() != "minio":
        return
    key = s.s3_access_key.strip()
    secret = s.s3_secret_key.strip()
    if not key or not secret:
        raise RuntimeError("启用 minio 附件时必须配置 S3_ACCESS_KEY 与 S3_SECRET_KEY")
    if (key, secret) in _WEAK_S3_PAIRS:
        raise RuntimeError("S3 凭据为已知弱默认值，请在 .env 中更换为强随机密钥")
