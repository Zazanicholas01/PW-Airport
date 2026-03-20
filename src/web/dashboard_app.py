import asyncio
import html
import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.db.db_functions import list_flights_in_sliding_window
from src.db.engine import get_engine
from src.db import models
from src.domain.status_constants import PERSONAL_AIRPORT, WINDOW_TIMEDELTA_HOURS

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_FILE = WEB_DIR / "templates" / "dashboard.html"
EVENTS_LOG_FILE = WEB_DIR.parent.parent / "data" / "logs" / "events.jsonl"
PLANES_DIR = STATIC_DIR / "planes"
PLANE_MODELS_DIR = PLANES_DIR / "models"
WINDOW_AIRPORT_ICAO = PERSONAL_AIRPORT
WINDOW_DURATION = timedelta(hours=WINDOW_TIMEDELTA_HOURS)
DASHBOARD_SESSION = sessionmaker(bind=get_engine(), future=True)


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


def _read_planes_on_ground_snapshot() -> dict[str, object]:
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


def _detail_field(label: str, value: str) -> str:
    return (
        '<div class="detail-field">'
        f'<div class="detail-label">{html.escape(label)}</div>'
        f'<div class="detail-value">{html.escape(value)}</div>'
        "</div>"
    )


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


def _detail_page(
    title: str,
    subtitle: str,
    fields: list[tuple[str, str]],
    image_url: str,
    image_alt: str,
    *,
    progress_percent: int = 0,
    progress_label: str = "Tracking unavailable",
    progress_start_label: str = "--:--",
    progress_end_label: str = "--:--",
) -> HTMLResponse:
    fields_markup = "".join(_detail_field(label, value) for label, value in fields)
    return HTMLResponse(
        f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(title)} - PW Airport</title>
    <style>
      :root {{
        --panel: rgba(16, 22, 29, 0.96);
        --panel-border: rgba(255, 176, 64, 0.2);
        --line: rgba(255, 176, 64, 0.12);
        --head: #ffd089;
        --text: #f7e6c1;
        --dim: #c4a97a;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        font-family: "Segoe UI", sans-serif;
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(255, 176, 64, 0.14), transparent 24%),
          linear-gradient(180deg, #091017 0%, #111822 100%);
      }}
      .page {{
        max-width: 1320px;
        margin: 0 auto;
        padding: 38px 28px 48px;
      }}
      .back-link {{
        display: inline-block;
        color: var(--head);
        text-decoration: none;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-size: 12px;
        margin-bottom: 22px;
      }}
      .detail-layout {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 28px;
      }}
      .detail-panel {{
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-radius: 22px;
        overflow: hidden;
        box-shadow: 0 22px 48px rgba(0, 0, 0, 0.35);
      }}
      .detail-copy {{
        padding: 30px;
      }}
      .detail-kicker {{
        color: var(--dim);
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 12px;
      }}
      .detail-title {{
        margin: 12px 0 8px;
        color: var(--head);
        font-size: 34px;
        line-height: 1.08;
      }}
      .detail-subtitle {{
        margin: 0 0 24px;
        color: var(--dim);
        font-size: 15px;
      }}
      .detail-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
      }}
      .detail-field {{
        padding: 14px 16px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: rgba(255, 176, 64, 0.04);
      }}
      .detail-label {{
        color: var(--dim);
        text-transform: uppercase;
        letter-spacing: 0.16em;
        font-size: 11px;
        margin-bottom: 8px;
      }}
      .detail-value {{
        font-size: 15px;
        font-weight: 700;
        overflow-wrap: anywhere;
      }}
      .detail-visual {{
        min-height: 520px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-start;
        position: relative;
        padding: 34px 28px 28px;
        background:
          radial-gradient(circle at top, rgba(255, 176, 64, 0.14), transparent 34%),
          linear-gradient(180deg, rgba(14, 20, 26, 0.98), rgba(9, 13, 18, 0.98));
      }}
      .detail-visual::before {{
        content: "";
        position: absolute;
        inset: 18px;
        border-radius: 18px;
        border: 1px solid rgba(255, 176, 64, 0.08);
      }}
      .detail-image {{
        position: relative;
        max-width: 92%;
        max-height: 420px;
        object-fit: contain;
        border-radius: 18px;
        box-shadow:
          0 26px 50px rgba(0, 0, 0, 0.34),
          0 10px 22px rgba(255, 176, 64, 0.12),
          inset 0 0 0 1px rgba(255, 255, 255, 0.04);
        filter: drop-shadow(0 24px 38px rgba(0, 0, 0, 0.28));
      }}
      .detail-progress {{
        position: relative;
        width: min(92%, 520px);
        margin-top: 24px;
      }}
      .detail-progress-meta {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
        color: var(--dim);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.14em;
      }}
      .detail-progress-track {{
        position: relative;
        height: 12px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(255, 176, 64, 0.08);
        border: 1px solid rgba(255, 176, 64, 0.14);
        box-shadow: inset 0 0 12px rgba(255, 176, 64, 0.08);
      }}
      .detail-progress-bar {{
        height: 100%;
        width: {max(0, min(100, progress_percent))}%;
        border-radius: inherit;
        background: linear-gradient(90deg, #ff9f1c, #ffd089);
        box-shadow: 0 0 18px rgba(255, 176, 64, 0.28);
      }}
      .detail-progress-plane {{
        position: absolute;
        top: 50%;
        left: {max(0, min(100, progress_percent))}%;
        width: 30px;
        height: 30px;
        transform: translate(-50%, -58%);
        filter:
          drop-shadow(0 10px 16px rgba(0, 0, 0, 0.34))
          drop-shadow(0 0 10px rgba(255, 176, 64, 0.22));
        pointer-events: none;
      }}
      .detail-progress-plane svg {{
        display: block;
        width: 100%;
        height: 100%;
      }}
      .detail-progress-times {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 10px;
        color: var(--text);
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.08em;
      }}
      @media (max-width: 920px) {{
        .detail-layout {{ grid-template-columns: 1fr; }}
        .detail-grid {{ grid-template-columns: 1fr; }}
        .detail-visual {{ min-height: 320px; }}
      }}
    </style>
  </head>
  <body>
    <div class="page">
      <a class="back-link" href="/">← Back to Dashboard</a>
      <div class="detail-layout">
        <aside class="detail-panel detail-visual">
          <img class="detail-image" src="{html.escape(image_url)}" alt="{html.escape(image_alt)}" />
          <div class="detail-progress">
            <div class="detail-progress-meta">
              <span>{html.escape(progress_label)}</span>
              <span>{max(0, min(100, progress_percent))}%</span>
            </div>
            <div class="detail-progress-track">
              <div class="detail-progress-bar"></div>
              <div class="detail-progress-plane" aria-hidden="true">
                <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="planeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stop-color="#ffe29f"/>
                      <stop offset="55%" stop-color="#ffb040"/>
                      <stop offset="100%" stop-color="#ff8a1f"/>
                    </linearGradient>
                  </defs>
                  <path fill="url(#planeGrad)" d="M58 29.5c1.7 0 3 1.3 3 3s-1.3 3-3 3H39.8l-8.5 18.8c-.5 1.1-1.7 1.7-2.9 1.4l-3.3-.8a2.5 2.5 0 0 1-1.6-3.5L29 35.5H18.7l-4.3 5.2c-.6.7-1.5 1-2.4.8l-3.5-.8c-1.7-.4-2.4-2.5-1.3-3.9l4.2-4.7H6c-1.7 0-3-1.3-3-3s1.3-3 3-3h5.4l-4.2-4.7c-1.1-1.3-.4-3.5 1.3-3.9l3.5-.8c.9-.2 1.8.1 2.4.8l4.3 5.2H29l-5.5-15.9a2.5 2.5 0 0 1 1.6-3.5l3.3-.8c1.2-.3 2.4.3 2.9 1.4l8.5 18.8H58Z"/>
                  <path fill="rgba(255,255,255,0.22)" d="M30 12.5 35.8 25H29.9l-3.5-10.4c-.2-.7.2-1.4.9-1.6l1.7-.4c.4-.1.8.1 1 .5Z"/>
                </svg>
              </div>
            </div>
            <div class="detail-progress-times">
              <span>{html.escape(progress_start_label)}</span>
              <span>{html.escape(progress_end_label)}</span>
            </div>
          </div>
        </aside>
        <section class="detail-panel">
          <div class="detail-copy">
            <div class="detail-kicker">PW Airport Detail</div>
            <h1 class="detail-title">{html.escape(title)}</h1>
            <p class="detail-subtitle">{html.escape(subtitle)}</p>
            <div class="detail-grid">{fields_markup}</div>
          </div>
        </section>
      </div>
    </div>
  </body>
</html>"""
    )


def flight_detail(flight_id: str) -> HTMLResponse:
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

        return _detail_page(
            title=str(getattr(flight, "icao", None) or flight_id),
            subtitle=f"{getattr(flight, 'origin', '--')} -> {getattr(flight, 'destination', '--')}",
            fields=[
                ("Flight ID", str(flight_id)),
                ("Status", str(getattr(flight, "status", "--") or "--")),
                ("Type", str(getattr(flight, "tipo", "--") or "--")),
                ("Origin", str(getattr(flight, "origin", "--") or "--")),
                ("Destination", str(getattr(flight, "destination", "--") or "--")),
                ("Departure", dep_label),
                ("Arrival", arr_label),
                ("Airplane", str(airplane_id or "--")),
                ("Plane Model", str(model or "--")),
                ("Airline", str(getattr(flight, "airline_code", "--") or "--")),
            ],
            image_url=_plane_image_url(model),
            image_alt=str(model or "Default plane"),
            progress_percent=progress_percent,
            progress_label=progress_label,
            progress_start_label=_progress_time_label(dep),
            progress_end_label=_progress_time_label(arr),
        )


def plane_detail(airplane_id: str) -> HTMLResponse:
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
        progress_percent, progress_label = _flight_progress(
            now_utc=_current_sim_now_utc(),
            departure_time=getattr(latest_flight, "departure_time", None) if latest_flight else None,
            arrival_time=getattr(latest_flight, "arrival_time", None) if latest_flight else None,
        )

        return _detail_page(
            title=str(airplane_id),
            subtitle=f"{getattr(airplane, 'model', '--')} / {getattr(airplane, 'status', '--')}",
            fields=[
                ("Airplane ID", str(airplane_id)),
                ("Status", str(getattr(airplane, "status", "--") or "--")),
                ("Model", str(getattr(airplane, "model", "--") or "--")),
                ("Type", str(getattr(airplane, "type", "--") or "--")),
                ("Range", str(getattr(airplane, "range", "--") or "--")),
                ("Speed", f"{float(getattr(airplane, 'speed', 0.0)):.2f}"),
                ("Stand", str(stand_id or "--")),
                ("Route", _path_endpoints_label(path)),
                ("Route ID", str(route_id or "--")),
                ("Flight", str(getattr(latest_flight, 'icao', None) or '--')),
            ],
            image_url=_plane_image_url(getattr(airplane, "model", None)),
            image_alt=str(getattr(airplane, "model", "Default plane")),
            progress_percent=progress_percent,
            progress_label=progress_label,
            progress_start_label=_progress_time_label(getattr(latest_flight, "departure_time", None) if latest_flight else None),
            progress_end_label=_progress_time_label(getattr(latest_flight, "arrival_time", None) if latest_flight else None),
        )


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(TEMPLATE_FILE, media_type="text/html")


app.get("/flight/{flight_id}")(flight_detail)
app.get("/plane/{airplane_id}")(plane_detail)


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


@app.websocket("/ws/planes-ground")
async def planes_ground_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            await websocket.send_json({"kind": "snapshot", "planes": _read_planes_on_ground_snapshot()})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
