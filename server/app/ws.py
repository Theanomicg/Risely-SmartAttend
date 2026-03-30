from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class AlertConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, class_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[class_id].add(websocket)

    async def disconnect(self, class_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[class_id].discard(websocket)

    async def broadcast(self, class_id: str, payload: dict) -> None:
        async with self._lock:
            targets = list(self._connections.get(class_id, set()))

        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self._connections[class_id].discard(websocket)


manager = AlertConnectionManager()
