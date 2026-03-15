import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.db.db_functions import list_flights_in_sliding_window
from src.domain.status_constants import PERSONAL_AIRPORT, WINDOW_TIMEDELTA_HOURS

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_FILE = WEB_DIR / "templates" / "dashboard.html"
EVENTS_LOG_FILE = WEB_DIR.parent.parent / "data" / "logs" / "events.jsonl"
WINDOW_AIRPORT_ICAO = PERSONAL_AIRPORT
WINDOW_DURATION = timedelta(hours=WINDOW_TIMEDELTA_HOURS)


def _format_log_timestamp(raw_ts: str | None) -> str:
    if not raw_ts:
        return "--:--:--"
    try:
        return datetime.fromisoformat(raw_ts).strftime("%H:%M:%S")
    except ValueError:
        return raw_ts


def _parse_log_event(line: str) -> dict[str, str] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if event.get("type") != "log":
        return None

    level = str(event.get("level") or "INFO").upper()
    subsystem = event.get("subsystem") or event.get("logger") or "-"
    fields = event.get("logger") if event.get("subsystem") else ""
    return {
        "ts": _format_log_timestamp(event.get("ts")),
        "level": level,
        "subsystem": str(subsystem),
        "message": str(event.get("message") or ""),
        "fields": str(fields or ""),
    }


def _parse_clock_event(line: str) -> dict[str, float | int | str] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if event.get("type") != "clock":
        return None

    sim_unix_ms = event.get("sim_unix_ms")
    time_scale = event.get("time_scale")
    sync_id = event.get("sync_id")
    ts = event.get("ts")
    if sim_unix_ms is None or time_scale is None or sync_id is None or not ts:
        return None

    return {
        "sim_unix_ms": int(sim_unix_ms),
        "time_scale": float(time_scale),
        "sync_id": int(sync_id),
        "ts": str(ts),
    }


def _read_recent_events(limit: int = 20) -> list[dict[str, str]]:
    if not EVENTS_LOG_FILE.exists():
        return []

    entries: deque[dict[str, str]] = deque(maxlen=limit)
    with EVENTS_LOG_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            parsed = _parse_log_event(line)
            if parsed:
                entries.append(parsed)
    return list(entries)


def _read_events_since(offset: int) -> tuple[list[dict[str, str]], int]:
    if not EVENTS_LOG_FILE.exists():
        return [], 0

    entries: list[dict[str, str]] = []
    with EVENTS_LOG_FILE.open("rb") as handle:
        handle.seek(offset)
        for raw_line in handle:
            line = raw_line.decode("utf-8", errors="ignore")
            parsed = _parse_log_event(line)
            if parsed:
                entries.append(parsed)
        return entries, handle.tell()


def _read_latest_clock_sync() -> dict[str, float | int | str] | None:
    if not EVENTS_LOG_FILE.exists():
        return None

    latest: dict[str, float | int | str] | None = None
    with EVENTS_LOG_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            parsed = _parse_clock_event(line)
            if parsed:
                latest = parsed
    return latest


def _current_sim_now_utc() -> datetime:
    latest = _read_latest_clock_sync()
    if latest is None:
        return datetime.now(timezone.utc)

    sync_ts = datetime.fromisoformat(str(latest["ts"]))
    if sync_ts.tzinfo is None:
        sync_ts = sync_ts.replace(tzinfo=timezone.utc)

    elapsed_real_ms = max(0.0, (datetime.now(timezone.utc) - sync_ts).total_seconds() * 1000.0)
    sim_unix_ms = float(latest["sim_unix_ms"]) + elapsed_real_ms * float(latest["time_scale"])
    return datetime.fromtimestamp(sim_unix_ms / 1000.0, tz=timezone.utc)


def _read_clock_syncs_since(offset: int) -> tuple[list[dict[str, float | int | str]], int]:
    if not EVENTS_LOG_FILE.exists():
        return [], 0

    entries: list[dict[str, float | int | str]] = []
    with EVENTS_LOG_FILE.open("rb") as handle:
        handle.seek(offset)
        for raw_line in handle:
            line = raw_line.decode("utf-8", errors="ignore")
            parsed = _parse_clock_event(line)
            if parsed:
                entries.append(parsed)
        return entries, handle.tell()


def _status_pill_class(status: str | None) -> str:
    normalized = str(status or "").lower()
    if normalized in {"scheduled", "standreserved"}:
        return "status-scheduled"
    if normalized in {"departing", "dep_ongoing", "landing", "lan_ongoing", "disembarking"}:
        return "status-landing"
    if normalized in {"completed"}:
        return "status-completed"
    return "status-default"


def _flight_reference_time(flight, airport_icao: str) -> datetime | None:
    origin = getattr(flight, "origin", None)
    destination = getattr(flight, "destination", None)

    if destination == airport_icao and getattr(flight, "arrival_time", None) is not None:
        return getattr(flight, "arrival_time", None)
    if origin == airport_icao and getattr(flight, "departure_time", None) is not None:
        return getattr(flight, "departure_time", None)
    if getattr(flight, "arrival_time", None) is not None:
        return getattr(flight, "arrival_time", None)
    return getattr(flight, "departure_time", None)


def _serialize_window_flight(*, flight, airport_icao: str, now_utc: datetime) -> dict[str, str | int]:
    reference_time = _flight_reference_time(flight, airport_icao)
    if reference_time is not None and reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    delta_min = None
    when_label = "--:--"
    if reference_time is not None:
        delta_min = round((reference_time - now_utc).total_seconds() / 60.0)
        when_label = reference_time.astimezone().strftime("%H:%M")

    origin = str(getattr(flight, "origin", "") or "")
    destination = str(getattr(flight, "destination", "") or "")
    status = str(getattr(flight, "status", "") or "")
    flight_code = str(getattr(flight, "icao", None) or getattr(flight, "id", "") or "")
    direction = "[ARR]" if destination == airport_icao else "[DEP]"

    return {
        "id": str(getattr(flight, "id", "") or ""),
        "direction": direction,
        "when": when_label,
        "delta_min": "--" if delta_min is None else int(delta_min),
        "flight": flight_code,
        "route": f"{origin} -> {destination}",
        "type": str(getattr(flight, "tipo", "") or ""),
        "status": status,
        "status_class": _status_pill_class(status),
        "airplane": str(getattr(flight, "airplane_id", None) or "--"),
    }


def _read_window_flights_snapshot() -> dict[str, object]:
    now_utc = _current_sim_now_utc()
    try:
        flights = list_flights_in_sliding_window(
            airport_icao=WINDOW_AIRPORT_ICAO,
            now_utc=now_utc,
            window=WINDOW_DURATION,
        )
        rows = [
            _serialize_window_flight(flight=flight, airport_icao=WINDOW_AIRPORT_ICAO, now_utc=now_utc)
            for flight in flights
        ]
        rows.sort(key=lambda row: (999999 if row["delta_min"] == "--" else abs(int(row["delta_min"])), str(row["flight"])))
    except Exception:
        logging.exception("[dashboard] failed to read window flights snapshot")
        rows = []

    return {
        "airport_icao": WINDOW_AIRPORT_ICAO,
        "window_minutes": int(WINDOW_DURATION.total_seconds() // 60),
        "generated_at": now_utc.isoformat(),
        "rows": rows,
    }


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(TEMPLATE_FILE, media_type="text/html")


@app.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"kind": "snapshot", "events": _read_recent_events(limit=20)})

    offset = EVENTS_LOG_FILE.stat().st_size if EVENTS_LOG_FILE.exists() else 0

    try:
        while True:
            await asyncio.sleep(1)

            if not EVENTS_LOG_FILE.exists():
                offset = 0
                continue

            file_size = EVENTS_LOG_FILE.stat().st_size
            if file_size < offset:
                offset = 0

            if file_size == offset:
                continue

            events, offset = _read_events_since(offset)
            if events:
                await websocket.send_json({"kind": "append", "events": events})
    except WebSocketDisconnect:
        return


@app.websocket("/ws/clock")
async def clock_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    latest = _read_latest_clock_sync()
    if latest:
        await websocket.send_json({"kind": "sync", "clock": latest})

    offset = EVENTS_LOG_FILE.stat().st_size if EVENTS_LOG_FILE.exists() else 0

    try:
        while True:
            await asyncio.sleep(0.5)

            if not EVENTS_LOG_FILE.exists():
                offset = 0
                continue

            file_size = EVENTS_LOG_FILE.stat().st_size
            if file_size < offset:
                offset = 0

            if file_size == offset:
                continue

            syncs, offset = _read_clock_syncs_since(offset)
            for sync in syncs:
                await websocket.send_json({"kind": "sync", "clock": sync})
    except WebSocketDisconnect:
        return


@app.websocket("/ws/window-flights")
async def window_flights_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            await websocket.send_json({"kind": "snapshot", "window": _read_window_flights_snapshot()})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
