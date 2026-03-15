from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class DashboardSubscriber:
    queue: asyncio.Queue[str]
    airport: str
    window_minutes: int


class DashboardSSEBus:
    def __init__(self) -> None:
        self.subscribers: set[DashboardSubscriber] = set()

    def subscribe(self, *, airport: str, window_minutes: int) -> DashboardSubscriber:
        subscriber = DashboardSubscriber(
            queue=asyncio.Queue(maxsize=32),
            airport=airport,
            window_minutes=window_minutes,
        )
        self.subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: DashboardSubscriber) -> None:
        self.subscribers.discard(subscriber)

    @staticmethod
    def encode(event_name: str, payload: dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"

    async def publish_event(self, event_name: str, payload: dict[str, Any]) -> None:
        await self._broadcast_preencoded(self.encode(event_name, payload))

    async def broadcast_snapshots(self, projection) -> None:
        dead: list[DashboardSubscriber] = []
        for subscriber in list(self.subscribers):
            try:
                snapshot = await projection.get_snapshot(
                    airport=subscriber.airport,
                    window_minutes=subscriber.window_minutes,
                )
                if subscriber.queue.full():
                    _ = subscriber.queue.get_nowait()
                subscriber.queue.put_nowait(self.encode("snapshot", snapshot))
            except Exception:
                dead.append(subscriber)
        for subscriber in dead:
            self.subscribers.discard(subscriber)
        if self.subscribers:
            logger.debug("[dashboard_sse] snapshots_broadcast subscribers=%s", len(self.subscribers))

    async def _broadcast_preencoded(self, message: str) -> None:
        dead: list[DashboardSubscriber] = []
        for subscriber in list(self.subscribers):
            try:
                if subscriber.queue.full():
                    _ = subscriber.queue.get_nowait()
                subscriber.queue.put_nowait(message)
            except Exception:
                dead.append(subscriber)
        for subscriber in dead:
            self.subscribers.discard(subscriber)
