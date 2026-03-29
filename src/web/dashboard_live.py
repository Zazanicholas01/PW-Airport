import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from src.web.dashboard_data import (
    EVENTS_LOG_FILE,
    read_clock_syncs_since,
    read_events_since,
    read_latest_clock_sync,
    read_planes_on_ground_snapshot,
    read_recent_events,
    read_window_flights_snapshot,
)


@dataclass
class DashboardState:
    latest_events: list[dict[str, str]] = field(default_factory=list)
    latest_clock: dict[str, float | int | str] | None = None
    latest_window: dict[str, object] = field(default_factory=lambda: {"rows": []})
    latest_planes: dict[str, object] = field(default_factory=lambda: {"rows": []})

    events_clients: set[WebSocket] = field(default_factory=set)
    clock_clients: set[WebSocket] = field(default_factory=set)
    window_clients: set[WebSocket] = field(default_factory=set)
    planes_clients: set[WebSocket] = field(default_factory=set)

    events_offset: int = 0
    clock_offset: int = 0

    events_task: asyncio.Task | None = None
    snapshots_task: asyncio.Task | None = None


dashboard_state = DashboardState()


async def _broadcast_json(clients: set[WebSocket], payload) -> None:

    stale: list[WebSocket] = []

    for client in list(clients):
        try:
            await client.send_json(payload)
        except Exception:
            stale.append(client)
    
    for client in stale:
        clients.discard(client)


def _snapshot_signature(snapshot) -> str:
    return json.dumps(snapshot, sort_keys=True, default=str)


async def _events_clock_loop() -> None:

    if EVENTS_LOG_FILE.exists():
        dashboard_state.latest_events = read_recent_events(limit=20)
        dashboard_state.latest_clock = read_latest_clock_sync()
        dashboard_state.events_offset = EVENTS_LOG_FILE.stat().st_size
        dashboard_state.clock_offset = dashboard_state.events_offset
    
    last_clock_sync_id = (
        int(dashboard_state.latest_clock["sync_id"])
        if dashboard_state.latest_clock and dashboard_state.latest_clock.get("sync_id") is not None
        else None
    )

    while True:
        try:

            # Wait for events log file to exist
            if not EVENTS_LOG_FILE.exists():
                await asyncio.sleep(1.0)
                continue

            file_size = EVENTS_LOG_FILE.stat().st_size
            if file_size < dashboard_state.events_offset:
                dashboard_state.events_offset = 0
                dashboard_state.clock_offset = 0
            
            if file_size > dashboard_state.events_offset:
                new_events, new_offset = read_events_since(dashboard_state.events_offset)
                dashboard_state.events_offset = new_offset

                if new_events:
                    dashboard_state.latest_events = (dashboard_state.latest_events + new_events)[-20:]
                    await _broadcast_json(
                        dashboard_state.events_clients,
                        {"kind": "append", "events": new_events},
                    )
            
            if file_size > dashboard_state.clock_offset:
                new_syncs, new_offset = read_clock_syncs_since(dashboard_state.clock_offset)
                dashboard_state.clock_offset = new_offset

                for sync in new_syncs:
                    sync_id = int(sync["sync_id"])
                    if last_clock_sync_id == sync_id:
                        continue

                    last_clock_sync_id = sync_id
                    dashboard_state.latest_clock = sync
                    await _broadcast_json(
                        dashboard_state.clock_clients,
                        {"kind": "sync", "clock": sync},
                    )
            
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[dashboard] events/clock loop failed")
            await asyncio.sleep(1.0)


async def _snapshot_loop() -> None:
    last_window_sig = ""
    last_planes_sig = ""

    while True:
        try:
            window_snapshot = read_window_flights_snapshot()
            window_sig = _snapshot_signature(window_snapshot)
            if window_sig != last_window_sig:
                last_window_sig = window_sig
                dashboard_state.latest_window = window_snapshot
                await _broadcast_json(
                    dashboard_state.window_clients,
                    {"kind": "snapshot", "window": window_snapshot},
                )
            
            planes_snapshot = read_planes_on_ground_snapshot()
            planes_sig = _snapshot_signature(planes_snapshot)
            if planes_sig != last_planes_sig:
                last_planes_sig = planes_sig
                dashboard_state.latest_planes = planes_snapshot
                await _broadcast_json(
                    dashboard_state.planes_clients,
                    {"kind": "snapshot", "planes": planes_snapshot},
                )
            
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[dashboard] Snapshot loop failed")
            await asyncio.sleep(2.0)


async def startup_dashboard_state() -> None:
    if dashboard_state.events_task is None or dashboard_state.events_task.done():
        dashboard_state.events_task = asyncio.create_task(_events_clock_loop())
    if dashboard_state.snapshots_task is None or dashboard_state.snapshots_task.done():
        dashboard_state.snapshots_task = asyncio.create_task(_snapshot_loop())


async def shutdown_dashboard_state() -> None:
    for task in (dashboard_state.events_task, dashboard_state.snapshots_task):
        if task is None:
            continue
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    dashboard_state.events_task = None
    dashboard_state.snapshots_task = None
