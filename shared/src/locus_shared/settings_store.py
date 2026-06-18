"""~/.agentpod/settings.json 读写与默认值。"""

from __future__ import annotations

import json
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .paths import agentpod_home, ensure_agentpod_home, expand_path


class LlmSection(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    auxiliary_vision_model: str = ""
    auxiliary_web_extract_model: str = ""
    auxiliary_compression_model: str = ""
    auxiliary_title_generation_model: str = ""
    auxiliary_approval_model: str = ""
    auxiliary_curator_model: str = ""
    auxiliary_skill_reflect_model: str = ""


class EmbeddingSection(BaseModel):
    model: str = "BAAI/bge-small-zh-v1.5"
    cache_dir: str = ""


class ToolsSection(BaseModel):
    tavily_api_key: str = ""
    jina_api_key: str = ""


class PathsSection(BaseModel):
    data_dir: str = ""


class SecretsSection(BaseModel):
    encryption_key: str = ""
    session_secret: str = ""
    internal_token: str = ""

    @classmethod
    def generate(cls) -> SecretsSection:
        from cryptography.fernet import Fernet

        return cls(
            encryption_key=Fernet.generate_key().decode("ascii"),
            session_secret=secrets.token_hex(32),
            internal_token=secrets.token_hex(32),
        )


class AppSection(BaseModel):
    timezone: str = "UTC"
    locale: str = "en"
    public_base_url: str = "http://127.0.0.1:21223"
    mcp_oauth_redirect_uri: str = "http://127.0.0.1:21223/api/oauth/mcp/callback"


class TerminalSection(BaseModel):
    enable_terminal: bool = True
    whitelist: str = "git,npm,node,python3,make"
    denylist: str = "sh,bash,zsh,dash,fish"


class DeveloperSection(BaseModel):
    devtools_enabled: bool = False


class QuickChatWindowBounds(BaseModel):
    x: int
    y: int


class DesktopSection(BaseModel):
    run_in_background: bool = False
    launch_at_login: bool = False
    quick_chat_enabled: bool = True
    quick_chat_shortcut: str = "cmd+shift+K"
    quick_chat_always_on_top: bool = False
    quick_chat_window_bounds: QuickChatWindowBounds | None = None


class SettingsDocument(BaseModel):
    llm: LlmSection = Field(default_factory=LlmSection)
    embedding: EmbeddingSection = Field(default_factory=EmbeddingSection)
    tools: ToolsSection = Field(default_factory=ToolsSection)
    terminal: TerminalSection = Field(default_factory=TerminalSection)
    developer: DeveloperSection = Field(default_factory=DeveloperSection)
    desktop: DesktopSection = Field(default_factory=DesktopSection)
    paths: PathsSection = Field(default_factory=PathsSection)
    secrets: SecretsSection = Field(default_factory=SecretsSection)
    app: AppSection = Field(default_factory=AppSection)


def settings_path() -> Path:
    return agentpod_home() / "settings.json"


def data_dir(doc: SettingsDocument | None = None) -> Path:
    raw = (doc or load_settings_document()).paths.data_dir.strip()
    if raw:
        return expand_path(raw)
    return ensure_agentpod_home()


def embedding_cache_dir(doc: SettingsDocument | None = None) -> Path:
    d = doc or load_settings_document()
    raw = d.embedding.cache_dir.strip()
    if raw:
        return expand_path(raw)
    path = data_dir(d) / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def host_sqlite_path(doc: SettingsDocument | None = None) -> Path:
    return data_dir(doc) / "host.sqlite"


def shared_skills_dir() -> Path | None:
    """打包进 app 的 skills 目录；开发时由 sidecar 注入。"""
    override = _bundled_skills_dir
    if override is not None:
        return override
    repo = Path(__file__).resolve().parents[3] / "shared-skills"
    return repo if repo.is_dir() else None


_bundled_skills_dir: Path | None = None


def set_bundled_skills_dir(path: Path | None) -> None:
    global _bundled_skills_dir
    _bundled_skills_dir = path


def _ensure_secrets(doc: SettingsDocument) -> SettingsDocument:
    changed = False
    secrets_section = doc.secrets
    if not secrets_section.encryption_key.strip():
        secrets_section = SecretsSection.generate()
        doc.secrets = secrets_section
        changed = True
    elif not secrets_section.session_secret.strip():
        secrets_section.session_secret = secrets.token_hex(32)
        changed = True
    elif not secrets_section.internal_token.strip():
        secrets_section.internal_token = secrets.token_hex(32)
        changed = True
    if changed:
        save_settings_document(doc)
    return doc


def load_settings_document(*, create: bool = True) -> SettingsDocument:
    path = settings_path()
    if not path.is_file():
        if not create:
            return SettingsDocument()
        ensure_agentpod_home()
        doc = SettingsDocument(secrets=SecretsSection.generate())
        save_settings_document(doc)
        return doc
    raw = json.loads(path.read_text(encoding="utf-8"))
    doc = SettingsDocument.model_validate(raw if isinstance(raw, dict) else {})
    return _ensure_secrets(doc)


def save_settings_document(doc: SettingsDocument) -> None:
    ensure_agentpod_home()
    path = settings_path()
    path.write_text(
        json.dumps(doc.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@lru_cache
def get_settings_document() -> SettingsDocument:
    return load_settings_document()


def clear_settings_cache() -> None:
    get_settings_document.cache_clear()


def apply_app_config_update(
    *,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    auxiliary_vision_model: str | None = None,
    auxiliary_web_extract_model: str | None = None,
    auxiliary_compression_model: str | None = None,
    auxiliary_title_generation_model: str | None = None,
    auxiliary_approval_model: str | None = None,
    auxiliary_curator_model: str | None = None,
    auxiliary_skill_reflect_model: str | None = None,
    tavily_api_key: str | None = None,
    jina_api_key: str | None = None,
    embedding_model: str | None = None,
    enable_terminal: bool | None = None,
    terminal_whitelist: str | None = None,
    terminal_denylist: str | None = None,
    devtools_enabled: bool | None = None,
) -> SettingsDocument:
    doc = load_settings_document()
    if llm_base_url is not None:
        doc.llm.base_url = llm_base_url.strip() or doc.llm.base_url
    if llm_model is not None:
        doc.llm.model = llm_model.strip() or doc.llm.model
    if llm_api_key is not None and llm_api_key.strip():
        doc.llm.api_key = llm_api_key.strip()
    if auxiliary_vision_model is not None:
        doc.llm.auxiliary_vision_model = auxiliary_vision_model.strip()
    if auxiliary_web_extract_model is not None:
        doc.llm.auxiliary_web_extract_model = auxiliary_web_extract_model.strip()
    if auxiliary_compression_model is not None:
        doc.llm.auxiliary_compression_model = auxiliary_compression_model.strip()
    if auxiliary_title_generation_model is not None:
        doc.llm.auxiliary_title_generation_model = auxiliary_title_generation_model.strip()
    if auxiliary_approval_model is not None:
        doc.llm.auxiliary_approval_model = auxiliary_approval_model.strip()
    if auxiliary_curator_model is not None:
        doc.llm.auxiliary_curator_model = auxiliary_curator_model.strip()
    if auxiliary_skill_reflect_model is not None:
        doc.llm.auxiliary_skill_reflect_model = auxiliary_skill_reflect_model.strip()
    if tavily_api_key is not None:
        doc.tools.tavily_api_key = tavily_api_key.strip()
    if jina_api_key is not None:
        doc.tools.jina_api_key = jina_api_key.strip()
    if embedding_model is not None:
        doc.embedding.model = embedding_model.strip() or doc.embedding.model
    if enable_terminal is not None:
        doc.terminal.enable_terminal = enable_terminal
    if terminal_whitelist is not None:
        doc.terminal.whitelist = terminal_whitelist.strip()
    if terminal_denylist is not None:
        doc.terminal.denylist = terminal_denylist.strip() or doc.terminal.denylist
    if devtools_enabled is not None:
        doc.developer.devtools_enabled = devtools_enabled
    save_settings_document(doc)
    clear_settings_cache()
    return doc


def get_app_timezone(doc: SettingsDocument | None = None) -> str:
    d = doc or load_settings_document()
    tz = d.app.timezone.strip()
    return tz or "UTC"


def set_app_timezone(timezone: str) -> SettingsDocument:
    doc = load_settings_document()
    doc.app.timezone = timezone.strip() or "UTC"
    save_settings_document(doc)
    clear_settings_cache()
    return doc


APP_LOCALES = frozenset({"zh", "en"})


def validate_app_locale(locale: str) -> str:
    value = (locale or "").strip().lower()
    if value not in APP_LOCALES:
        raise ValueError(f"invalid locale: {locale}")
    return value


def get_app_locale(doc: SettingsDocument | None = None) -> str:
    d = doc or load_settings_document()
    try:
        return validate_app_locale(d.app.locale)
    except ValueError:
        return "en"


def set_app_locale(locale: str) -> SettingsDocument:
    doc = load_settings_document()
    doc.app.locale = validate_app_locale(locale)
    save_settings_document(doc)
    clear_settings_cache()
    return doc


def export_settings_document() -> dict[str, Any]:
    """导出完整 settings.json 内容（含 secrets），用于备份与迁移。"""
    doc = load_settings_document()
    return doc.model_dump(mode="json")


def import_settings_document(raw: dict[str, Any]) -> SettingsDocument:
    """用导入内容完全覆盖当前 settings.json。"""
    doc = SettingsDocument.model_validate(raw if isinstance(raw, dict) else {})
    save_settings_document(doc)
    clear_settings_cache()
    return _ensure_secrets(doc)


def reload_runtime_config() -> None:
    """保存 settings.json 后刷新进程内配置缓存。"""
    clear_settings_cache()
    try:
        from agentpod_host.config import get_settings as get_host_settings

        get_host_settings.cache_clear()
    except ImportError:
        pass
    try:
        from agentpod_agent.config import get_settings as get_agent_settings

        get_agent_settings.cache_clear()
    except ImportError:
        pass
    try:
        from agentpod_shared.local_embeddings import _load_model

        _load_model.cache_clear()
    except Exception:
        pass


def app_config_for_api(doc: SettingsDocument | None = None) -> dict[str, Any]:
    d = doc or load_settings_document()
    return {
        "llm": {
            "base_url": d.llm.base_url,
            "model": d.llm.model,
            "api_key_configured": bool(d.llm.api_key.strip()),
            "auxiliary_vision_model": d.llm.auxiliary_vision_model,
            "auxiliary_web_extract_model": d.llm.auxiliary_web_extract_model,
            "auxiliary_compression_model": d.llm.auxiliary_compression_model,
            "auxiliary_title_generation_model": d.llm.auxiliary_title_generation_model,
            "auxiliary_approval_model": d.llm.auxiliary_approval_model,
            "auxiliary_curator_model": d.llm.auxiliary_curator_model,
            "auxiliary_skill_reflect_model": d.llm.auxiliary_skill_reflect_model,
        },
        "tools": {
            "tavily_api_key_configured": bool(d.tools.tavily_api_key.strip()),
            "jina_api_key_configured": bool(d.tools.jina_api_key.strip()),
        },
        "embedding": {
            "model": d.embedding.model,
        },
        "terminal": {
            "enable_terminal": d.terminal.enable_terminal,
            "whitelist": d.terminal.whitelist,
            "denylist": d.terminal.denylist,
        },
        "developer": {
            "devtools_enabled": d.developer.devtools_enabled,
        },
        "desktop": {
            "run_in_background": d.desktop.run_in_background,
            "launch_at_login": d.desktop.launch_at_login,
            "quick_chat_enabled": d.desktop.quick_chat_enabled,
            "quick_chat_shortcut": d.desktop.quick_chat_shortcut,
            "quick_chat_always_on_top": d.desktop.quick_chat_always_on_top,
            "quick_chat_window_bounds": (
                d.desktop.quick_chat_window_bounds.model_dump(mode="json")
                if d.desktop.quick_chat_window_bounds
                else None
            ),
        },
        "app": {
            "timezone": get_app_timezone(d),
            "locale": get_app_locale(d),
        },
    }


def document_to_host_kwargs(doc: SettingsDocument | None = None) -> dict[str, Any]:
    from .ports import agentpod_base_url

    d = doc or get_settings_document()
    home = data_dir(d)
    skills = shared_skills_dir()
    return {
        "mcp_oauth_redirect_uri": d.app.mcp_oauth_redirect_uri,
        "encryption_key": d.secrets.encryption_key,
        "session_secret": d.secrets.session_secret,
        "host_sqlite_path": str(host_sqlite_path(d)),
        "agent_service_url": agentpod_base_url(),
        "agent_internal_token": d.secrets.internal_token,
        "llm_base_url": d.llm.base_url,
        "llm_api_key": d.llm.api_key,
        "llm_model": d.llm.model,
        "auxiliary_vision_model": d.llm.auxiliary_vision_model,
        "auxiliary_web_extract_model": d.llm.auxiliary_web_extract_model,
        "auxiliary_compression_model": d.llm.auxiliary_compression_model,
        "auxiliary_title_generation_model": d.llm.auxiliary_title_generation_model,
        "auxiliary_approval_model": d.llm.auxiliary_approval_model,
        "auxiliary_curator_model": d.llm.auxiliary_curator_model,
        "auxiliary_skill_reflect_model": d.llm.auxiliary_skill_reflect_model,
        "tavily_api_key": d.tools.tavily_api_key,
        "jina_api_key": d.tools.jina_api_key,
        "embedding_base_url": "local",
        "embedding_model": d.embedding.model,
        "attachment_storage": "local",
        "attachment_max_bytes": 25 * 1024 * 1024,
        "public_base_url": d.app.public_base_url,
        "enable_terminal": d.terminal.enable_terminal,
        "terminal_whitelist": d.terminal.whitelist,
        "terminal_denylist": d.terminal.denylist,
        "internal_network_guard_enabled": False,
        "internal_rate_limit_per_minute": 600,
    }


def document_to_agent_kwargs(doc: SettingsDocument | None = None) -> dict[str, Any]:
    from .ports import agentpod_base_url, agentpod_llm_internal_url

    d = doc or get_settings_document()
    home = data_dir(d)
    skills = shared_skills_dir()
    token = d.secrets.internal_token
    return {
        "internal_token": token,
        "llm_base_url": agentpod_llm_internal_url(),
        "embedding_base_url": "local",
        "embedding_model": d.embedding.model,
        "host_internal_url": agentpod_base_url(),
        "data_dir": home,
        "shared_skills_dir": skills or (home / "skills"),
        "attachment_storage": "local",
        "attachment_max_bytes": 25 * 1024 * 1024,
        "enable_terminal": d.terminal.enable_terminal,
        "terminal_whitelist": d.terminal.whitelist,
        "terminal_denylist": d.terminal.denylist,
    }
