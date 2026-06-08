"""当前运行环境信息工具（容器视角）。"""

from __future__ import annotations

import json

from ..host_settings import HostSettingsError, get_timezone
from ..logging import get_logger
from ..workspace import get_workspace_id, workspace_data_dir
from .base import Tool, ToolResult, register_builtin

log = get_logger("tools.user_info")


async def _get_current_user(_args: dict) -> ToolResult:
    timezone = None
    try:
        timezone = await get_timezone()
    except HostSettingsError as exc:
        log.debug("get_current_user_timezone_failed", error=str(exc))
        timezone = None
    payload = {
        "workspace_id": get_workspace_id(),
        "timezone": timezone,
        "data_dir": str(workspace_data_dir()),
        "note": "不返回模型配置或 API Key 等凭据。",
    }
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        metadata=payload,
    )


register_builtin(
    Tool(
        name="get_current_user",
        description=(
            "获取当前会话的运行环境与基础上下文（工作区、用户时区、数据目录等）。"
            "适用于诊断环境确认场景。"
            "不用于读取业务数据，也不返回敏感凭据或模型配置。"
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_get_current_user,
    )
)
