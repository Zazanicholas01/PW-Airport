# src/web/dashboard_app.py
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.db.db_functions import list_flights_in_sliding_window
from src.utils.event_log import log_dir

from sqlalchemy import select
from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker
from src.db import models

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_FILE = WEB_DIR / "templates" / "dashboard.html"
EVENTS_FILE = Path(log_dir()) / "events.jsonl"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _to_iso(dt: Any) -> str | None:
    """Normalize datetimes into ISO strings"""

    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def _flight_to_dict(f: Any) -> dict[str, Any]:
    """Convert flight record into dict"""

    return {
        "id": getattr(f, "id", None),
        "icao": getattr(f, "icao", None),
        "origin": getattr(f, "origin", None),
        "destination": getattr(f, "destination", None),
        "departure_time": _to_iso(getattr(f, "departure_time", None)),
        "arrival_time": _to_iso(getattr(f, "arrival_time", None)),
        "tipo": getattr(f, "tipo", None),
        "status": getattr(f, "status", None),
        "airplane_id": getattr(f, "airplane_id", None),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(TEMPLATE_FILE, media_type="text/html")


@app.get("/api/window")
def api_window(
    airport: str = "LIAG", 
    window_minutes: int = 60,
    now_unix_ms: int | None = None) -> dict[str, Any]:
    """Defines the route for the sliding window"""

    # Computes actual time based on simulated time current UTC time
    now = (
        datetime.fromtimestamp(now_unix_ms / 1000.0, tz=timezone.utc)
        if now_unix_ms is not None
        else datetime.now(timezone.utc)
        )
    
    # Lists flights in the sliding window
    flights = list_flights_in_sliding_window(
        airport_icao=airport,
        now_utc=now,
        window=timedelta(minutes=window_minutes),
    )

    # Sort flights by time
    def sort_key(f: Any):
        dep = getattr(f, "departure_time", None)
        arr = getattr(f, "arrival_time", None)
        t = dep or arr
        if isinstance(t, datetime) and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t or datetime.max.replace(tzinfo=timezone.utc)
    flights = sorted(flights, key=sort_key)

    return {"now": now.isoformat(), "count": len(flights), "flights": [_flight_to_dict(f) for f in flights]}

@app.get("/api/flight/{flight_id}")
def api_flight(flight_id: str) -> dict[str, Any]:
    """Fetch a single flight by id (used by the UI when it falls out of /api/window)."""

    if not isinstance(flight_id, str) or not flight_id.strip():
        raise HTTPException(status_code=400, detail="Invalid flight id")

    with Session() as session:
        # UI routes are keyed by `flightIdForRow()`, which prefers `icao` over DB PK `id`.
        # Accept either.
        f = session.get(models.Flight, flight_id)
        if f is None:
            f = session.scalars(
                select(models.Flight).where(models.Flight.icao == flight_id)
            ).first()
        if f is None:
            raise HTTPException(status_code=404, detail="Flight not found")
        return _flight_to_dict(f)


Engine = get_engine()
Session = sessionmaker(bind=Engine, future=True)


@app.get("/api/planes")
def api_planes(now_unix_ms: int | None = None) -> dict[str, Any]:
    """Defines route for planes HTML"""

    # Get planes / stands / paths from DB
    with Session() as session:
        planes = list(session.scalars(select(models.Airplane)).all())
        stands = list(session.scalars(select(models.Stand)).all())
        paths = list(session.scalars(select(models.Path)).all())
    
    # Build look up dict to map airplane_id --> stand
    stand_by_plane: dict[str, Any] = {
        s.airplane_id: s for s in stands
        if isinstance(getattr(s, "airplane_id", None), str) and s.airplane_id
    }

    # Build look up dict to map path.id --> path
    path_by_id: dict[int, Any] = {
        p.id: p for p in paths
        if isinstance(getattr(p, "id", None), int)
    }

    # Build every plane row
    def plane_row(p: Any) -> dict[str, Any]:
        pid = getattr(p, "id", None)
        stand = stand_by_plane.get(pid) if isinstance(pid, str) else None
        route_id = getattr(p, "route_id", None)
        path = path_by_id.get(route_id) if isinstance(route_id, int) else None

        # Return JSON data for every plane
        return {
            "id": pid,
            "status": getattr(p, "status", None),
            "type": getattr(p, "type", None),
            "range": getattr(p, "range", None),
            "model": getattr(p, "model", None),
            "speed": getattr(p, "speed", None),
            "position": getattr(stand, "position", None),

            "stand_id": getattr(stand, "id", None),
            "stand_status": getattr(stand, "status", None),

            "route_id": route_id,
            "route_source": getattr(path, "source", None),
            "route_destination": getattr(path, "destination", None),
        }

    # Sort for nicer UI
    status_rank = {"Parked": 0, "Disembarking": 1}
    items = sorted(
        (plane_row(p) for p in planes),
        key=lambda x: (status_rank.get(x.get("status"), 99), str(x.get("id") or "")),
    )

    return {"count": len(items), "planes": items}

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, tail: int = 50) -> None:
    """Events websocket route to drive Live Events and trigger refreshes"""

    await ws.accept()

    # Create directory for events JSON file
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Send recent history (Last N lines)
    if EVENTS_FILE.exists():
        try:
            lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-max(0, int(tail)):]
            for line in lines:
                if line.strip():
                    await ws.send_text(line)
        except Exception:
            pass

    # Tail the file for new events appended at bottom of the file
    f = EVENTS_FILE.open("a+", encoding="utf-8")
    f.seek(0, 2)

    # If new line arrives, send it immediately otherwise sleep for 0.25s
    # On Websocket disconnect returns, always close the file in finally block
    try:
        while True:
            line = f.readline()
            if line:
                await ws.send_text(line.rstrip("\n"))
            else:
                await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
    finally:
        f.close()
