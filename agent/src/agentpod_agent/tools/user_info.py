"""当前运行环境信息工具。"""

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
        "note": "Does not return model config or API keys.",
    }
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        metadata=payload,
    )


register_builtin(
    Tool(
        name="get_current_user",
        description=(
            "Runtime environment and basic context for the current session (workspace, user timezone, data dirs, etc.)."
            "For environment diagnostics."
            "Not for business data; does not return credentials or model config."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_get_current_user,
    )
)
