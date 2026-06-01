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
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "timezone": timezone,
        "data_dir": str(workspace_data_dir()),
        "shared_skills_dir": str(settings.shared_skills_dir),
        "note": "P0 仅提供容器内可见的用户基础信息。",
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

