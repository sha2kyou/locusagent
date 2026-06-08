"""Host 启动初始化。"""

from __future__ import annotations

from .db import get_session
from .workspaces import ensure_default_workspace


async def ensure_host_ready() -> None:
    async with get_session() as session:
        await ensure_default_workspace(session)
