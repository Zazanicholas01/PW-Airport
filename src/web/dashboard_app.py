import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from src.app.container import AppContainer, build_container
from src.db import db_functions, models
from src.db.engine import get_db
from src.utils.event_log import log_dir
from src.web.dashboard_bridge import run_dashboard_event_bridge
from src.web.dashboard_projection import DashboardProjectionService, _flight_to_dict

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_FILE = WEB_DIR / "templates" / "dashboard.html"
EVENTS_FILE = Path(log_dir()) / "events.jsonl"
SIM_EVENT_WS_URL = os.getenv("SIM_EVENT_WS_URL", "ws://host.docker.internal:8765/observer")
DASHBOARD_DISABLE_EVENT_BRIDGE = os.getenv("DASHBOARD_DISABLE_EVENT_BRIDGE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
logger = logging.getLogger(__name__)


def _db_dep(request: Request):
    yield from get_db(request.app.state.Session)


def create_app(*, container: AppContainer) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.Session = container.Session
    app.state.projection = DashboardProjectionService(
        session_factory=container.Session,
        events_file=EVENTS_FILE,
    )
    db_functions.configure_session_factory(container.Session)
    return app


async def _projection_warmup(app: FastAPI) -> None:
    projection: DashboardProjectionService = app.state.projection
    projection.ensure_clock_fresh()
    projection.load_recent_logs_from_events_file()
    projection.set_bridge_status("disabled" if DASHBOARD_DISABLE_EVENT_BRIDGE else "connecting")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _projection_warmup(app)
    bridge_task: asyncio.Task | None = None
    if DASHBOARD_DISABLE_EVENT_BRIDGE:
        logger.warning("[dashboard_bridge] disabled via DASHBOARD_DISABLE_EVENT_BRIDGE")
    else:
        bridge_task = asyncio.create_task(
            run_dashboard_event_bridge(
                projection=app.state.projection,
                observer_url=SIM_EVENT_WS_URL,
            )
        )
    try:
        yield
    finally:
        if bridge_task is not None:
            bridge_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bridge_task


app = create_app(container=build_container())


@app.get("/")
def index() -> FileResponse:
    return FileResponse(TEMPLATE_FILE, media_type="text/html")


@app.get("/api/dashboard")
async def api_dashboard(
    request: Request,
    airport: str = Query(default="LIAG"),
    window_minutes: int = Query(default=60, ge=5, le=360),
) -> dict:
    projection: DashboardProjectionService = request.app.state.projection
    snapshot = await projection.get_snapshot(airport=airport, window_minutes=window_minutes)
    return {
        **snapshot,
        "logs": projection.get_recent_logs(limit=50),
    }


@app.get("/api/clock")
async def api_clock(request: Request) -> dict:
    projection: DashboardProjectionService = request.app.state.projection
    payload = projection.current_clock_payload()
    return payload["clock"]


@app.get("/api/flight/{flight_id}")
def api_flight(flight_id: str, session: OrmSession = Depends(_db_dep)) -> dict:
    if not isinstance(flight_id, str) or not flight_id.strip():
        raise HTTPException(status_code=400, detail="Invalid flight id")

    flight = session.get(models.Flight, flight_id)
    if flight is None:
        flight = session.scalars(select(models.Flight).where(models.Flight.icao == flight_id)).first()
    if flight is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return _flight_to_dict(flight)


@app.get("/api/planes")
def api_planes(session: OrmSession = Depends(_db_dep)) -> dict:
    planes = list(session.scalars(select(models.Airplane)).all())
    stands = list(session.scalars(select(models.Stand)).all())
    paths = list(session.scalars(select(models.Path)).all())

    stand_by_plane = {
        s.airplane_id: s for s in stands
        if isinstance(getattr(s, "airplane_id", None), str) and s.airplane_id
    }
    path_by_id = {
        p.id: p for p in paths
        if isinstance(getattr(p, "id", None), int)
    }

    def plane_row(p) -> dict:
        pid = getattr(p, "id", None)
        stand = stand_by_plane.get(pid) if isinstance(pid, str) else None
        route_id = getattr(p, "route_id", None)
        path = path_by_id.get(route_id) if isinstance(route_id, int) else None
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

    items = sorted((plane_row(p) for p in planes), key=lambda x: str(x.get("id") or ""))
    return {"count": len(items), "planes": items}
