import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from src.domain.status_constants import DASHBOARD_COMMANDS
from src.web.dashboard_data import (
    EVENTS_LOG_FILE,
    _parse_clock_event,
    _parse_scheduler_window_event,
    parse_latest_clock_from_lines,
    parse_latest_scheduler_window_from_lines,
    read_recent_jsonl_lines,
)


@dataclass
class DashboardState:
    latest_clock: dict[str, float | int | str] | None = None
    latest_window: dict[str, object] = field(default_factory=lambda: {"rows": []})

    clock_clients: set[WebSocket] = field(default_factory=set)
    window_clients: set[WebSocket] = field(default_factory=set)
    redirect_clients: set[WebSocket] = field(default_factory=set)

    events_offset: int = 0

    dashboard_task: asyncio.Task | None = None


dashboard_state = DashboardState()


def _parse_dashboard_redirect_event(line: str) -> dict[str, str] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if event.get("type") != "dashboard_redirect":
        return None

    if event.get("command") != DASHBOARD_COMMANDS.HIGHLIGHT_FLIGHT:
        return None

    flight_id = str(event.get("flight_id") or "")
    redirect_url = str(event.get("redirect_url") or "")
    if not flight_id or not redirect_url:
        return None

    return {
        "flight_id": flight_id,
        "redirect_url": redirect_url,
    }


async def _broadcast_json(clients: set[WebSocket], payload) -> None:

    stale: list[WebSocket] = []

    logging.info(
        "[dashboard] broadcast payload kind=%s clients=%d",
        payload.get("kind") if isinstance(payload, dict) else type(payload).__name__,
        len(clients),
    )

    for client in list(clients):
        try:
            await client.send_json(payload)
        except Exception:
            stale.append(client)
    
    for client in stale:
        clients.discard(client)


def _read_dashboard_events_since(offset: int, *, include_clock: bool):
    if not EVENTS_LOG_FILE.exists():
        return [], [], [], 0

    clock_syncs = []
    scheduler_windows = []
    redirects = []

    with EVENTS_LOG_FILE.open("rb") as handle:
        handle.seek(offset)

        for raw_line in handle:
            line = raw_line.decode("utf-8", errors="ignore")

            if include_clock:
                clock_sync = _parse_clock_event(line)
                if clock_sync:
                    clock_syncs.append(clock_sync)

            scheduler_window = _parse_scheduler_window_event(line)
            if scheduler_window:
                scheduler_windows.append(scheduler_window)

            redirect = _parse_dashboard_redirect_event(line)
            if redirect:
                redirects.append(redirect)

        return clock_syncs, scheduler_windows, redirects, handle.tell()


async def _dashboard_loop() -> None:

    if EVENTS_LOG_FILE.exists():
        startup_lines = read_recent_jsonl_lines(limit=50)
        dashboard_state.latest_clock = parse_latest_clock_from_lines(startup_lines)
        dashboard_state.latest_window = parse_latest_scheduler_window_from_lines(startup_lines) or {"rows": []}
        dashboard_state.events_offset = EVENTS_LOG_FILE.stat().st_size
    
    last_clock_sync_id = (
        int(dashboard_state.latest_clock["sync_id"])
        if dashboard_state.latest_clock and dashboard_state.latest_clock.get("sync_id") is not None
        else None
    )
    while True:
        try:
            if not EVENTS_LOG_FILE.exists():
                await asyncio.sleep(1.0)
                continue

            file_size = EVENTS_LOG_FILE.stat().st_size
            if file_size < dashboard_state.events_offset:
                dashboard_state.events_offset = 0
            
            if file_size > dashboard_state.events_offset:
                include_clock = bool(dashboard_state.clock_clients) or dashboard_state.latest_clock is None
                new_syncs, new_windows, new_redirects, new_offset = _read_dashboard_events_since(
                    dashboard_state.events_offset,
                    include_clock=include_clock,
                )
                dashboard_state.events_offset = new_offset

                for sync in new_syncs:
                    if not dashboard_state.clock_clients:
                        dashboard_state.latest_clock = sync
                        continue

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

                for redirect in new_redirects:
                    logging.info(
                        "[dashboard] redirect event flight_id=%s url=%s redirect_clients=%d",
                        redirect["flight_id"],
                        redirect["redirect_url"],
                        len(dashboard_state.redirect_clients),
                    )
                    await _broadcast_json(
                        dashboard_state.redirect_clients,
                        {
                            "kind": "redirect",
                            "command": DASHBOARD_COMMANDS.HIGHLIGHT_FLIGHT,
                            "flight_id": redirect["flight_id"],
                            "url": redirect["redirect_url"],
                        },
                    )
            
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[dashboard] window/clock loop failed")
            await asyncio.sleep(1.0)

async def startup_dashboard_state() -> None:
    if dashboard_state.dashboard_task is None or dashboard_state.dashboard_task.done():
        dashboard_state.dashboard_task = asyncio.create_task(_dashboard_loop())


async def shutdown_dashboard_state() -> None:
    if dashboard_state.dashboard_task is not None:
        dashboard_state.dashboard_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dashboard_state.dashboard_task

    dashboard_state.dashboard_task = None
