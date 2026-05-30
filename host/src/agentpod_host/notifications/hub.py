"""通知 WebSocket 连接池：按 user_id 推送新消息。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from ..logging import get_logger

log = get_logger("notifications.hub")


class NotificationHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._clients: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.setdefault(user_id, set()).add(ws)
        log.info("ws_connected", user_id=user_id, clients=len(self._clients.get(user_id, ())))

    async def disconnect(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            group = self._clients.get(user_id)
            if not group:
                return
            group.discard(ws)
            if not group:
                self._clients.pop(user_id, None)

    async def publish(self, user_id: int, event: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients.get(user_id, set()))
        if not targets:
            return
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)


hub = NotificationHub()
