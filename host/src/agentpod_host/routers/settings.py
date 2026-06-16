"""应用设置：时区与应用配置（settings.json）。"""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from agentpod_shared.settings_store import (
    app_config_for_api,
    apply_app_config_update,
    get_app_locale,
    get_app_timezone,
    reload_runtime_config,
    set_app_locale,
    set_app_timezone,
    validate_app_locale,
)
from agentpod_shared.activity_log import list_activity_logs, record_activity

from ..auth import AuthContext, require_session
from ..scheduled_tasks import recalc_task_schedules, validate_timezone
from ..usage import UsageSummaryOut, usage_summary

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TimezoneConfigIn(BaseModel):
    timezone: str = Field(..., min_length=1, max_length=64)


class TimezoneConfigOut(BaseModel):
    timezone: str


class LocaleConfigIn(BaseModel):
    locale: str = Field(..., min_length=2, max_length=8)


class LocaleConfigOut(BaseModel):
    locale: str


class AppSectionOut(BaseModel):
    timezone: str
    locale: str


class LlmConfigOut(BaseModel):
    base_url: str
    model: str
    api_key_configured: bool
    auxiliary_vision_model: str = ""
    auxiliary_web_extract_model: str = ""
    auxiliary_compression_model: str = ""
    auxiliary_title_generation_model: str = ""
    auxiliary_approval_model: str = ""
    auxiliary_curator_model: str = ""
    auxiliary_skill_reflect_model: str = ""


class ToolsConfigOut(BaseModel):
    tavily_api_key_configured: bool
    jina_api_key_configured: bool


class EmbeddingConfigOut(BaseModel):
    model: str


class TerminalConfigOut(BaseModel):
    enable_terminal: bool
    whitelist: str
    denylist: str


class AppConfigOut(BaseModel):
    llm: LlmConfigOut
    tools: ToolsConfigOut
    embedding: EmbeddingConfigOut
    terminal: TerminalConfigOut
    app: AppSectionOut


class ActivityLogEntryOut(BaseModel):
    id: int
    ts: str
    category: str
    action: str
    message: str
    workspace_id: str | None = None
    level: str = "info"
    detail: dict | None = None


class ActivityLogsOut(BaseModel):
    items: list[ActivityLogEntryOut]


class BackendLogsOut(BaseModel):
    lines: list[str]
    path: str


class AppConfigIn(BaseModel):
    llm_base_url: str | None = Field(default=None, max_length=512)
    llm_model: str | None = Field(default=None, max_length=128)
    llm_api_key: str | None = Field(default=None, max_length=512)
    auxiliary_vision_model: str | None = Field(default=None, max_length=128)
    auxiliary_web_extract_model: str | None = Field(default=None, max_length=128)
    auxiliary_compression_model: str | None = Field(default=None, max_length=128)
    auxiliary_title_generation_model: str | None = Field(default=None, max_length=128)
    auxiliary_approval_model: str | None = Field(default=None, max_length=128)
    auxiliary_curator_model: str | None = Field(default=None, max_length=128)
    auxiliary_skill_reflect_model: str | None = Field(default=None, max_length=128)
    tavily_api_key: str | None = Field(default=None, max_length=512)
    jina_api_key: str | None = Field(default=None, max_length=512)
    embedding_model: str | None = Field(default=None, max_length=256)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=8)
    enable_terminal: bool | None = None
    terminal_whitelist: str | None = Field(default=None, max_length=2048)
    terminal_denylist: str | None = Field(default=None, max_length=2048)


@router.get("/usage-summary", response_model=UsageSummaryOut)
async def read_usage_summary(ctx: AuthContext = Depends(require_session)) -> UsageSummaryOut:
    _ = ctx
    return await usage_summary()


@router.get("/activity-logs", response_model=ActivityLogsOut)
async def read_activity_logs(
    limit: int = 200,
    after_id: int | None = None,
    ctx: AuthContext = Depends(require_session),
) -> ActivityLogsOut:
    _ = ctx
    rows = list_activity_logs(limit=limit, after_id=after_id)
    return ActivityLogsOut(items=[ActivityLogEntryOut.model_validate(r) for r in rows])


@router.get("/backend-logs", response_model=BackendLogsOut)
async def read_backend_logs(
    lines: int = 2000,
    ctx: AuthContext = Depends(require_session),
) -> BackendLogsOut:
    _ = ctx
    line_limit = max(1, min(lines, 5000))
    home = Path(os.environ.get("AGENTPOD_HOME", Path.home() / ".agentpod"))
    log_path = home / "desktop-backend.log"
    if not log_path.is_file():
        return BackendLogsOut(lines=[], path=str(log_path))
    buf: deque[str] = deque(maxlen=line_limit)
    with log_path.open(errors="replace") as f:
        for line in f:
            buf.append(line.rstrip("\n"))
    return BackendLogsOut(lines=list(buf), path=str(log_path))


@router.get("/timezone", response_model=TimezoneConfigOut)
async def read_timezone(ctx: AuthContext = Depends(require_session)) -> TimezoneConfigOut:
    _ = ctx
    return TimezoneConfigOut(timezone=get_app_timezone())


@router.put("/timezone", response_model=TimezoneConfigOut)
async def save_timezone(
    payload: TimezoneConfigIn,
    ctx: AuthContext = Depends(require_session),
) -> TimezoneConfigOut:
    _ = ctx
    try:
        tz = validate_timezone(payload.timezone)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    set_app_timezone(tz)
    await recalc_task_schedules()
    record_activity("settings", "timezone_save", f"Timezone saved: {tz}")
    return TimezoneConfigOut(timezone=tz)


@router.get("/locale", response_model=LocaleConfigOut)
async def read_locale(ctx: AuthContext = Depends(require_session)) -> LocaleConfigOut:
    _ = ctx
    return LocaleConfigOut(locale=get_app_locale())


@router.put("/locale", response_model=LocaleConfigOut)
async def save_locale(
    payload: LocaleConfigIn,
    ctx: AuthContext = Depends(require_session),
) -> LocaleConfigOut:
    _ = ctx
    try:
        locale = validate_app_locale(payload.locale)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    set_app_locale(locale)
    record_activity("settings", "locale_save", f"Locale saved: {locale}")
    return LocaleConfigOut(locale=locale)


@router.get("/app-config", response_model=AppConfigOut)
async def read_app_config(ctx: AuthContext = Depends(require_session)) -> AppConfigOut:
    _ = ctx
    return AppConfigOut.model_validate(app_config_for_api())


@router.put("/app-config", response_model=AppConfigOut)
async def save_app_config(
    payload: AppConfigIn,
    request: Request,
    ctx: AuthContext = Depends(require_session),
) -> AppConfigOut:
    _ = ctx
    _ = request
    if payload.llm_base_url is not None and not payload.llm_base_url.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="llm_base_url required")
    if payload.llm_model is not None and not payload.llm_model.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="llm_model required")

    if payload.timezone is not None:
        try:
            validate_timezone(payload.timezone)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if payload.locale is not None:
        try:
            validate_app_locale(payload.locale)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    doc = apply_app_config_update(
        llm_base_url=payload.llm_base_url,
        llm_api_key=payload.llm_api_key,
        llm_model=payload.llm_model,
        auxiliary_vision_model=payload.auxiliary_vision_model,
        auxiliary_web_extract_model=payload.auxiliary_web_extract_model,
        auxiliary_compression_model=payload.auxiliary_compression_model,
        auxiliary_title_generation_model=payload.auxiliary_title_generation_model,
        auxiliary_approval_model=payload.auxiliary_approval_model,
        auxiliary_curator_model=payload.auxiliary_curator_model,
        auxiliary_skill_reflect_model=payload.auxiliary_skill_reflect_model,
        tavily_api_key=payload.tavily_api_key,
        jina_api_key=payload.jina_api_key,
        embedding_model=payload.embedding_model,
        enable_terminal=payload.enable_terminal,
        terminal_whitelist=payload.terminal_whitelist,
        terminal_denylist=payload.terminal_denylist,
    )
    if payload.timezone is not None:
        doc = set_app_timezone(validate_timezone(payload.timezone))
    if payload.locale is not None:
        doc = set_app_locale(validate_app_locale(payload.locale))
    reload_runtime_config()

    if payload.timezone is not None:
        await recalc_task_schedules()

    record_activity("settings", "app_config_save", "App config saved")
    return AppConfigOut.model_validate(app_config_for_api(doc))
