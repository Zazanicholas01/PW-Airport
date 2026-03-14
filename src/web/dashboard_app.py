# src/web/dashboard_app.py
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import contextlib, json, os
import logging
from contextlib import asynccontextmanager
import websockets

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.db.db_functions import list_flights_in_sliding_window
from src.db.engine import get_db
from src.utils.event_log import log_dir

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from src.db import models
from src.app.container import AppContainer, build_container
from src.db import db_functions

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_FILE = WEB_DIR / "templates" / "dashboard.html"
EVENTS_FILE = Path(log_dir()) / "events.jsonl"
SIM_EVENT_WS_URL = os.getenv("SIM_EVENT_WS_URL", "ws://host.docker.internal:8765/observer")
logger = logging.getLogger(__name__)


class DashboardEventBus:
    def __init__(self) -> None:
        self.clients = set()

    async def connect_client(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
    
    def disconnect_client(self, ws: WebSocket) -> None:
        self.clients.discard(ws)
    
    async def publish_text(self, text: str) -> None:
        if not self.clients:
            return

        dead = []
        for ws in self.clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        
        for ws in dead:
            self.clients.discard(ws)


event_bus = DashboardEventBus()


@dataclass
class DashboardClockState:
    sim_unix_ms: int | None = None
    time_scale: float | None = None
    observed_at: datetime | None = None

    def update_from_message(self, payload: dict[str, Any]) -> None:
        raw_now_ms = payload.get("sim_unix_ms")
        raw_time_scale = payload.get("time_scale")

        try:
            sim_unix_ms = int(raw_now_ms)
        except (TypeError, ValueError):
            sim_unix_ms = None

        try:
            time_scale = float(raw_time_scale)
        except (TypeError, ValueError):
            time_scale = None

        if sim_unix_ms is not None:
            self.sim_unix_ms = sim_unix_ms
        if time_scale is not None:
            self.time_scale = time_scale
        if sim_unix_ms is not None or time_scale is not None:
            self.observed_at = datetime.now(timezone.utc)

    def snapshot_event(self) -> str | None:
        if self.sim_unix_ms is None:
            return None

        payload = {
            "type": "clock",
            "sim_unix_ms": self.sim_unix_ms,
            "time_scale": self.time_scale,
        }
        return json.dumps(payload, separators=(",", ":"))

    def now(self) -> datetime | None:
        if self.sim_unix_ms is None:
            return None
        return datetime.fromtimestamp(self.sim_unix_ms / 1000.0, tz=timezone.utc)


dashboard_clock = DashboardClockState()


def _load_latest_clock_from_events_file() -> None:
    if not EVENTS_FILE.exists():
        logger.warning("[dashboard_clock] events_file_missing path=%s", EVENTS_FILE)
        return

    try:
        lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        logger.exception("[dashboard_clock] events_file_read_failed path=%s", EVENTS_FILE)
        return

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == "clock":
            dashboard_clock.update_from_message(payload)
            logger.info(
                "[dashboard_clock] loaded_from_file path=%s sim_unix_ms=%s time_scale=%s observed_at=%s",
                EVENTS_FILE,
                dashboard_clock.sim_unix_ms,
                dashboard_clock.time_scale,
                dashboard_clock.observed_at.isoformat() if dashboard_clock.observed_at else None,
            )
            return

    logger.warning("[dashboard_clock] no_clock_event_found_in_file path=%s", EVENTS_FILE)


def _ensure_dashboard_clock_fresh(max_age_seconds: float = 2.0) -> None:
    observed_at = dashboard_clock.observed_at
    if observed_at is None:
        logger.info("[dashboard_clock] cache_empty -> loading from file")
        _load_latest_clock_from_events_file()
        return

    age = (datetime.now(timezone.utc) - observed_at).total_seconds()
    if age > max_age_seconds:
        logger.info(
            "[dashboard_clock] cache_stale age_s=%.3f threshold_s=%.3f -> loading from file",
            age,
            max_age_seconds,
        )
        _load_latest_clock_from_events_file()


async def backend_event_bridge() -> None:
    while True:
        try:
            logger.info("[dashboard_bridge] connecting observer=%s", SIM_EVENT_WS_URL)
            async with websockets.connect(SIM_EVENT_WS_URL) as ws:
                logger.info("[dashboard_bridge] connected observer=%s", SIM_EVENT_WS_URL)
                async for message in ws:
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        payload = None

                    if isinstance(payload, dict) and payload.get("type") == "clock":
                        dashboard_clock.update_from_message(payload)
                        logger.info(
                            "[dashboard_bridge] clock_update sim_unix_ms=%s time_scale=%s observed_at=%s",
                            dashboard_clock.sim_unix_ms,
                            dashboard_clock.time_scale,
                            dashboard_clock.observed_at.isoformat() if dashboard_clock.observed_at else None,
                        )
                    await event_bus.publish_text(message)
        except Exception:
            logger.exception("[dashboard_bridge] disconnected observer=%s", SIM_EVENT_WS_URL)
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bridge_task = asyncio.create_task(backend_event_bridge())
    try:
        yield
    finally:
        bridge_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bridge_task


def _db_dep(request: Request):
    yield from get_db(request.app.state.Session)


def create_app(*, container: AppContainer) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.Session = container.Session

    # Ensure db_functions uses the same injected Session factory.
    db_functions.configure_session_factory(container.Session)
    return app


# Default app for uvicorn: `uvicorn src.web.dashboard_app:app ...`
app = create_app(container=build_container())


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
    window_minutes: int = 60) -> dict[str, Any]:
    """Defines the route for the sliding window"""

    _ensure_dashboard_clock_fresh()

    cached_now = dashboard_clock.now()
    if cached_now is not None:
        now = cached_now
        now_source = "observer"
    else:
        now = datetime.now(timezone.utc)
        now_source = "realtime"

    logger.info(
        "[api_window] airport=%s window_minutes=%s now_source=%s resolved_now=%s cached_sim_unix_ms=%s cached_time_scale=%s observed_at=%s",
        airport,
        window_minutes,
        now_source,
        now.isoformat(),
        dashboard_clock.sim_unix_ms,
        dashboard_clock.time_scale,
        dashboard_clock.observed_at.isoformat() if dashboard_clock.observed_at else None,
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

    return {
        "now": now.isoformat(),
        "now_source": now_source,
        "time_scale": dashboard_clock.time_scale,
        "count": len(flights),
        "flights": [_flight_to_dict(f) for f in flights],
    }

@app.get("/api/flight/{flight_id}")
def api_flight(flight_id: str, session: OrmSession = Depends(_db_dep)) -> dict[str, Any]:
    """Fetch a single flight by id (used by the UI when it falls out of /api/window)."""

    if not isinstance(flight_id, str) or not flight_id.strip():
        raise HTTPException(status_code=400, detail="Invalid flight id")

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


@app.get("/api/planes")
def api_planes(session: OrmSession = Depends(_db_dep)) -> dict[str, Any]:
    """Defines route for planes HTML"""

    # Get planes / stands / paths from DB
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

    _ensure_dashboard_clock_fresh()
    await event_bus.connect_client(ws)
    logger.info(
        "[ws_events] client_connected tail=%s cached_sim_unix_ms=%s cached_time_scale=%s observed_at=%s",
        tail,
        dashboard_clock.sim_unix_ms,
        dashboard_clock.time_scale,
        dashboard_clock.observed_at.isoformat() if dashboard_clock.observed_at else None,
    )

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

    latest_clock = dashboard_clock.snapshot_event()
    if latest_clock is not None:
        with contextlib.suppress(Exception):
            await ws.send_text(latest_clock)
            logger.info(
                "[ws_events] sent_cached_clock tail=%s sim_unix_ms=%s time_scale=%s",
                tail,
                dashboard_clock.sim_unix_ms,
                dashboard_clock.time_scale,
            )

    try:
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        logger.info("[ws_events] client_disconnected tail=%s", tail)
        event_bus.disconnect_client(ws)
    finally:
        event_bus.disconnect_client(ws)
