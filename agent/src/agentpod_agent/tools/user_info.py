"""当前登录用户信息工具（容器视角）。"""

from __future__ import annotations

import json

from ..config import get_settings
from ..host_settings import HostSettingsError, get_timezone
from ..logging import get_logger
from ..workspace import get_workspace_id, workspace_data_dir
from .base import Tool, ToolResult, register_builtin

log = get_logger("tools.user_info")


async def _get_current_user(_args: dict) -> ToolResult:
    from ..core.models import resolve_model

    settings = get_settings()
    timezone = None
    try:
        timezone = await get_timezone()
    except HostSettingsError as exc:
        log.debug("get_current_user_timezone_failed", error=str(exc))
        timezone = None
    payload = {
        "user_id": settings.user_id,
        "workspace_id": get_workspace_id(),
        "models": {
            "main": resolve_model("main"),
            "vision": resolve_model("vision"),
            "web_extract": resolve_model("web_extract"),
            "compression": resolve_model("compression"),
            "title_generation": resolve_model("title_generation"),
            "approval": resolve_model("approval"),
            "curator": resolve_model("curator"),
            "skill_reflect": resolve_model("skill_reflect"),
            "memory_autostore": resolve_model("memory_autostore"),
        },
        "timezone": timezone,
        "data_dir": str(workspace_data_dir()),
        "shared_skills_dir": str(settings.shared_skills_dir),
        "note": "模型由宿主环境变量注入；不返回 API Key 等凭据。",
    }
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        metadata=payload,
    )


register_builtin(
    Tool(
        name="get_current_user",
        description=(
            "获取当前会话的运行身份与基础上下文（user_id、模型配置、用户时区、数据目录等）。"
            "适用于诊断“我是谁/当前模型是什么/数据落在哪”的环境确认场景。"
            "不用于读取业务数据，也不返回敏感凭据明文。"
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_get_current_user,
    )
)
