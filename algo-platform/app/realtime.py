from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass
class WSMessage:
    type: str
    data: dict[str, Any]


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: WSMessage) -> None:
        payload = json.dumps({"type": message.type, "data": message.data})
        async with self._lock:
            connections = list(self._connections)
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                await self.disconnect(ws)

    def connection_count(self) -> int:
        return len(self._connections)
