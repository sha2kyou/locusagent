"""当前登录用户信息工具（容器视角）。"""

from __future__ import annotations

import json

from ..config import get_settings
from .base import Tool, ToolResult, register_builtin


async def _get_current_user(_args: dict) -> ToolResult:
    settings = get_settings()
    payload = {
        "user_id": settings.user_id,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "data_dir": str(settings.data_dir),
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
        description="获取当前登录用户基础信息（user_id、模型配置与工作目录）。",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_get_current_user,
    )
)

