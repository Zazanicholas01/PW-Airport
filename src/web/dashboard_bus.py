from __future__ import annotations

import asyncio
from typing import Any


class DashboardEventBus:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(q)

    async def publish(self, event: dict[str, Any]) -> None:
        dead = []
        for q in list(self._queues):
            try:
                if q.full():
                    _ = q.get_nowait()
                q.put_nowait(event)
            except Exception:
                dead.append(q)
        for q in dead:
            self._queues.discard(q)
