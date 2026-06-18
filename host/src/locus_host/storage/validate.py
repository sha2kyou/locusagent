"""附件存储配置校验。"""

from __future__ import annotations

from locus_shared.settings_store import data_dir

from ..config import Settings, get_settings


def validate_attachment_storage(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    if s.attachment_storage.strip().lower() != "local":
        raise RuntimeError(f"unsupported attachment storage: {s.attachment_storage}")
    data_dir().joinpath("attachments").mkdir(parents=True, exist_ok=True)
