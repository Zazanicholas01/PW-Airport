import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.db import models
from src.db.db_functions import list_flights_in_sliding_window
from src.db.engine import get_engine
from src.domain.status_constants import PERSONAL_AIRPORT, WINDOW_TIMEDELTA_HOURS


WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
EVENTS_LOG_FILE = WEB_DIR.parent.parent / "data" / "logs" / "events.jsonl"
PLANES_DIR = STATIC_DIR / "planes"
PLANE_MODELS_DIR = PLANES_DIR / "models"
WINDOW_AIRPORT_ICAO = PERSONAL_AIRPORT
WINDOW_DURATION = timedelta(hours=WINDOW_TIMEDELTA_HOURS)
DASHBOARD_SESSION = sessionmaker(bind=get_engine(), future=True)

DETAIL_CACHE_TTL_SECONDS = 2.0
FLIGHT_DETAIL_CACHE = {}
PLANE_DETAIL_CACHE = {}


def _cache_get(cache, key) -> dict[str, object] | None:

    # Retrieve cache data by key
    cached = cache.get(key)
    if cached is None:
        return None
    
    # Separate timestamp and payload
    cached_at, payload = cached

    # Check TTL on cache to pop and cleanup
    if time.monotonic() - cached_at > DETAIL_CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    
    return payload


def _read_flight_detail_snapshot(flight_id: str) -> dict[str, object]:
    with DASHBOARD_SESSION() as session:
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            raise HTTPException(status_code=404, detail="Flight not found")

        airplane_id = getattr(flight, "airplane_id", None)
        airplane = session.get(models.Airplane, airplane_id) if airplane_id else None

        dep = getattr(flight, "departure_time", None)
        arr = getattr(flight, "arrival_time", None)

        dep_label = dep.astimezone().strftime("%Y-%m-%d %H:%M:%S") if dep else "--"
        arr_label = arr.astimezone().strftime("%Y-%m-%d %H:%M:%S") if arr else "--"

        model = getattr(airplane, "model", None) if airplane else None
        progress_percent, progress_label = _flight_progress(
            now_utc=_current_sim_now_utc(),
            departure_time=dep,
            arrival_time=arr,
        )

        return {
            "title": str(getattr(flight, "icao", None) or flight_id),
            "subtitle": f"{getattr(flight, 'origin', '--')} -> {getattr(flight, 'destination', '--')}",
            "fields": [
                ("Flight ID", str(flight_id), "flight_id"),
                ("Status", str(getattr(flight, "status", "--") or "--"), "status"),
                ("Type", str(getattr(flight, "tipo", "--") or "--"), "type"),
                ("Origin", str(getattr(flight, "origin", "--") or "--"), "origin"),
                ("Destination", str(getattr(flight, "destination", "--") or "--"), "destination"),
                ("Departure", dep_label, "departure"),
                ("Arrival", arr_label, "arrival"),
                ("Airplane", str(airplane_id or "--"), "airplane"),
                ("Plane Model", str(model or "--"), "plane_model"),
                ("Airline", str(getattr(flight, "airline_code", "--") or "--"), "airline"),
            ],
            "image_url": _plane_image_url(model),
            "image_alt": str(model or "Default plane"),
            "progress_percent": progress_percent,
            "progress_label": progress_label,
            "progress_start_label": _progress_time_label(dep),
            "progress_end_label": _progress_time_label(arr),
            "progress_start_unix_ms": int(dep.timestamp() * 1000) if dep else None,
            "progress_end_unix_ms": int(arr.timestamp() * 1000) if arr else None,
            "detail_api_path": f"/api/flight/{flight_id}",
        }
    

def get_flight_detail_snapshot_cached(flight_id: str) -> dict[str, object]:
    cached = _cache_get(FLIGHT_DETAIL_CACHE, flight_id)
    if cached is not None:
        return cached

    snapshot = _read_flight_detail_snapshot(flight_id)
    FLIGHT_DETAIL_CACHE[flight_id] = (time.monotonic(), snapshot)
    return snapshot


def _read_plane_detail_snapshot(airplane_id: str) -> dict[str, object]:
    with DASHBOARD_SESSION() as session:
        airplane = session.get(models.Airplane, airplane_id)
        if airplane is None:
            raise HTTPException(status_code=404, detail="Plane not found")

        stand_id = session.execute(
            select(models.Stand.id).where(models.Stand.airplane_id == airplane_id)
        ).scalar_one_or_none()

        route_id = getattr(airplane, "route_id", None)
        path = session.get(models.Path, route_id) if route_id is not None else None

        latest_flight = session.execute(
            select(models.Flight)
            .where(models.Flight.airplane_id == airplane_id)
            .order_by(models.Flight.departure_time.desc(), models.Flight.arrival_time.desc())
        ).scalars().first()

        dep = getattr(latest_flight, "departure_time", None) if latest_flight else None
        arr = getattr(latest_flight, "arrival_time", None) if latest_flight else None

        progress_percent, progress_label = _flight_progress(
            now_utc=_current_sim_now_utc(),
            departure_time=dep,
            arrival_time=arr,
        )

        return {
            "title": str(airplane_id),
            "subtitle": f"{getattr(airplane, 'model', '--')} / {getattr(airplane, 'status', '--')}",
            "fields": [
                ("Airplane ID", str(airplane_id), "airplane_id"),
                ("Status", str(getattr(airplane, "status", "--") or "--"), "status"),
                ("Model", str(getattr(airplane, "model", "--") or "--"), "model"),
                ("Type", str(getattr(airplane, "type", "--") or "--"), "type"),
                ("Range", str(getattr(airplane, "range", "--") or "--"), "range"),
                ("Speed", f"{float(getattr(airplane, 'speed', 0.0)):.2f}", "speed"),
                ("Stand", str(stand_id or "--"), "stand"),
                ("Route", _path_endpoints_label(path), "route"),
                ("Route ID", str(route_id or "--"), "route_id"),
                ("Flight", str(getattr(latest_flight, 'icao', None) or '--'), "flight"),
            ],
            "image_url": _plane_image_url(getattr(airplane, "model", None)),
            "image_alt": str(getattr(airplane, "model", "Default plane")),
            "progress_percent": progress_percent,
            "progress_label": progress_label,
            "progress_start_label": _progress_time_label(dep),
            "progress_end_label": _progress_time_label(arr),
            "progress_start_unix_ms": int(dep.timestamp() * 1000) if dep else None,
            "progress_end_unix_ms": int(arr.timestamp() * 1000) if arr else None,
            "detail_api_path": f"/api/plane/{airplane_id}",
        }



def get_plane_detail_snapshot_cached(airplane_id: str) -> dict[str, object]:
    cached = _cache_get(PLANE_DETAIL_CACHE, airplane_id)
    if cached is not None:
        return cached

    snapshot = _read_plane_detail_snapshot(airplane_id)
    PLANE_DETAIL_CACHE[airplane_id] = (time.monotonic(), snapshot)
    return snapshot


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


def read_recent_events(limit: int = 20) -> list[dict[str, str]]:
    if not EVENTS_LOG_FILE.exists():
        return []

    entries: deque[dict[str, str]] = deque(maxlen=limit)
    with EVENTS_LOG_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            parsed = _parse_log_event(line)
            if parsed:
                entries.append(parsed)
    return list(entries)


def read_events_since(offset: int) -> tuple[list[dict[str, str]], int]:
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


def read_latest_clock_sync() -> dict[str, float | int | str] | None:
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
    latest = read_latest_clock_sync()
    if latest is None:
        return datetime.now(timezone.utc)

    sync_ts = datetime.fromisoformat(str(latest["ts"]))
    if sync_ts.tzinfo is None:
        sync_ts = sync_ts.replace(tzinfo=timezone.utc)

    elapsed_real_ms = max(0.0, (datetime.now(timezone.utc) - sync_ts).total_seconds() * 1000.0)
    sim_unix_ms = float(latest["sim_unix_ms"]) + elapsed_real_ms * float(latest["time_scale"])
    return datetime.fromtimestamp(sim_unix_ms / 1000.0, tz=timezone.utc)


def read_clock_syncs_since(offset: int) -> tuple[list[dict[str, float | int | str]], int]:
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
    if normalized in {"parked"}:
        return "status-parked"
    if normalized in {"scheduled", "standreserved"}:
        return "status-scheduled"
    if normalized in {"reserved"}:
        return "status-default"
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

    departure_time = getattr(flight, "departure_time", None)
    arrival_time = getattr(flight, "arrival_time", None)
    if departure_time is not None and departure_time.tzinfo is None:
        departure_time = departure_time.replace(tzinfo=timezone.utc)
    if arrival_time is not None and arrival_time.tzinfo is None:
        arrival_time = arrival_time.replace(tzinfo=timezone.utc)

    dep_label = "--:--"
    arr_label = "--:--"
    reference_unix_ms = None
    if reference_time is not None:
        reference_unix_ms = int(reference_time.timestamp() * 1000)
    if departure_time is not None:
        dep_label = departure_time.astimezone().strftime("%H:%M")
    if arrival_time is not None:
        arr_label = arrival_time.astimezone().strftime("%H:%M")

    origin = str(getattr(flight, "origin", "") or "")
    destination = str(getattr(flight, "destination", "") or "")
    status = str(getattr(flight, "status", "") or "")
    flight_code = str(getattr(flight, "icao", None) or getattr(flight, "id", "") or "")
    direction = "arrival" if destination == airport_icao else "departure"

    return {
        "id": str(getattr(flight, "id", "") or ""),
        "direction": direction,
        "dep_time": dep_label,
        "arr_time": arr_label,
        "reference_unix_ms": reference_unix_ms,
        "flight": flight_code,
        "route": f"{origin} -> {destination}",
        "type": str(getattr(flight, "tipo", "") or ""),
        "status": status,
        "status_class": _status_pill_class(status),
        "airplane": str(getattr(flight, "airplane_id", None) or "--"),
    }


def read_window_flights_snapshot() -> dict[str, object]:
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
        rows.sort(
            key=lambda row: (
                999999999999 if row["reference_unix_ms"] is None else abs(int(row["reference_unix_ms"]) - int(now_utc.timestamp() * 1000)),
                str(row["flight"]),
            )
        )
    except Exception:
        logging.exception("[dashboard] failed to read window flights snapshot")
        rows = []

    return {
        "airport_icao": WINDOW_AIRPORT_ICAO,
        "window_minutes": int(WINDOW_DURATION.total_seconds() // 60),
        "generated_at": now_utc.isoformat(),
        "rows": rows,
    }


def _path_endpoints_label(path) -> str:
    if path is None:
        return "--"
    source = str(getattr(path, "source", "") or "")
    destination = str(getattr(path, "destination", "") or "")
    if not source or not destination:
        return "--"
    return f"{source} -> {destination}"


def _serialize_ground_plane(*, stand, airplane, path) -> dict[str, str]:
    status = str(getattr(airplane, "status", "") or "")
    speed_value = getattr(airplane, "speed", None)
    speed = "--" if speed_value is None else f"{float(speed_value):.2f}"
    return {
        "airplane": str(getattr(airplane, "id", None) or "--"),
        "status": status,
        "status_class": _status_pill_class(status),
        "model": str(getattr(airplane, "model", None) or "--"),
        "type": str(getattr(airplane, "type", None) or "--"),
        "range": str(getattr(airplane, "range", None) or "--"),
        "speed": speed,
        "stand": str(getattr(stand, "id", None) or "--"),
        "route": _path_endpoints_label(path),
    }


def read_planes_on_ground_snapshot() -> dict[str, object]:
    try:
        with DASHBOARD_SESSION() as session:
            rows = []
            stand_rows = session.execute(
                select(models.Stand, models.Airplane, models.Path)
                .join(models.Airplane, models.Stand.airplane_id == models.Airplane.id)
                .outerjoin(models.Path, models.Airplane.route_id == models.Path.id)
                .order_by(models.Stand.id.asc())
            ).all()

            for stand, airplane, path in stand_rows:
                rows.append(
                    _serialize_ground_plane(
                        stand=stand,
                        airplane=airplane,
                        path=path,
                    )
                )

            return {"rows": rows}
    except Exception:
        logging.exception("[dashboard] failed to read planes on ground snapshot")
        return {"rows": []}


def _normalize_plane_model_name(model: str | None) -> str | None:
    if not model:
        return None
    return str(model).strip().lower().replace("_", "-")


def _plane_image_url(model: str | None) -> str:
    normalized = _normalize_plane_model_name(model)
    if normalized:
        candidate = PLANE_MODELS_DIR / f"{normalized}.png"
        if candidate.exists():
            return f"/static/planes/models/{candidate.name}"
    return "/static/planes/_default.png"


def _flight_progress(*, now_utc: datetime, departure_time: datetime | None, arrival_time: datetime | None) -> tuple[int, str]:
    if departure_time is None or arrival_time is None:
        return 0, "Tracking unavailable"
    if departure_time.tzinfo is None:
        departure_time = departure_time.replace(tzinfo=timezone.utc)
    if arrival_time.tzinfo is None:
        arrival_time = arrival_time.replace(tzinfo=timezone.utc)

    total_seconds = max((arrival_time - departure_time).total_seconds(), 1.0)
    elapsed_seconds = (now_utc - departure_time).total_seconds()
    progress = max(0, min(100, round((elapsed_seconds / total_seconds) * 100)))

    if now_utc < departure_time:
        return progress, "Scheduled"
    if now_utc > arrival_time:
        return progress, "Arrived"
    return progress, "Live Tracking"


def _progress_time_label(value: datetime | None) -> str:
    if value is None:
        return "--:--"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%H:%M")
