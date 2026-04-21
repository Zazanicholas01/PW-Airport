import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

from src.web.dashboard_data import (
    EVENTS_LOG_FILE,
    _parse_clock_event,
    _parse_log_event,
    _parse_scheduler_window_event,
    parse_latest_clock_from_lines,
    parse_latest_scheduler_window_from_lines,
    parse_recent_events_from_lines,
    read_planes_on_ground_snapshot,
    read_recent_jsonl_lines,
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


def _snapshot_signature(snapshot) -> tuple:
    rows = snapshot.get("rows") or []
    return tuple(
        (
            row.get("id") or row.get("airplane"),
            row.get("status"),
            row.get("airplane"),
            row.get("stand"),
            row.get("route"),
            row.get("reference_unix_ms"),
        )
        for row in rows
    )


def _read_dashboard_events_since(offset: int):
    if not EVENTS_LOG_FILE.exists():
        return [], [], [], 0

    log_events = []
    clock_syncs = []
    scheduler_windows = []

    with EVENTS_LOG_FILE.open("rb") as handle:
        handle.seek(offset)

        for raw_line in handle:
            line = raw_line.decode("utf-8", errors="ignore")

            log_event = _parse_log_event(line)
            if log_event:
                log_events.append(log_event)

            clock_sync = _parse_clock_event(line)
            if clock_sync:
                clock_syncs.append(clock_sync)

            scheduler_window = _parse_scheduler_window_event(line)
            if scheduler_window:
                scheduler_windows.append(scheduler_window)

        return log_events, clock_syncs, scheduler_windows, handle.tell()


async def _events_clock_loop() -> None:

    if EVENTS_LOG_FILE.exists():
        startup_lines = read_recent_jsonl_lines(limit=50)
        dashboard_state.latest_events = parse_recent_events_from_lines(startup_lines, limit=20)
        dashboard_state.latest_clock = parse_latest_clock_from_lines(startup_lines)
        dashboard_state.latest_window = parse_latest_scheduler_window_from_lines(startup_lines) or {"rows": []}
        dashboard_state.events_offset = EVENTS_LOG_FILE.stat().st_size
    
    last_clock_sync_id = (
        int(dashboard_state.latest_clock["sync_id"])
        if dashboard_state.latest_clock and dashboard_state.latest_clock.get("sync_id") is not None
        else None
    )
    last_events_heartbeat = 0.0

    while True:
        try:

            # Wait for events log file to exist
            if not EVENTS_LOG_FILE.exists():
                await asyncio.sleep(1.0)
                continue

            file_size = EVENTS_LOG_FILE.stat().st_size
            if file_size < dashboard_state.events_offset:
                dashboard_state.events_offset = 0
            
            if file_size > dashboard_state.events_offset:
                new_events, new_syncs, new_windows, new_offset = _read_dashboard_events_since(
                    dashboard_state.events_offset
                )
                dashboard_state.events_offset = new_offset

                if new_events:
                    dashboard_state.latest_events = (dashboard_state.latest_events + new_events)[-20:]
                    await _broadcast_json(
                        dashboard_state.events_clients,
                        {"kind": "append", "events": new_events[-50:]},
                    )

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

                if new_windows:
                    latest_window = new_windows[-1]
                    dashboard_state.latest_window = latest_window
                    await _broadcast_json(
                        dashboard_state.window_clients,
                        {"kind": "snapshot", "window": latest_window},
                    )

            now_monotonic = time.monotonic()
            if dashboard_state.events_clients and (now_monotonic - last_events_heartbeat) >= 15.0:
                last_events_heartbeat = now_monotonic
                await _broadcast_json(
                    dashboard_state.events_clients,
                    {"kind": "heartbeat"},
                )
            
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[dashboard] events/clock loop failed")
            await asyncio.sleep(1.0)


async def _snapshot_loop() -> None:
    last_planes_sig = ""

    while True:
        try:
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
