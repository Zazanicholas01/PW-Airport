from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any

from src.transport.loops.flight_actions import FlightActions

@dataclass(frozen=True)
class SessionContext:
    bus: Any
    setup_bus: Any
    runtime_bus: Any

    clock: Any
    clock_lock: asyncio.Lock
    clock_changed: asyncio.Event

    prefab_store: Any
    graph: Any
    world_state: Any
    Session: Any

    airport_icao: str

    flight_actions: FlightActions
