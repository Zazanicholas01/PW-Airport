from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.web.dashboard_data import (
    get_flight_detail_snapshot_cached,
    get_plane_detail_snapshot_cached,
    read_window_flights_snapshot,
)
from src.web.dashboard_live import (
    dashboard_state,
    shutdown_dashboard_state,
    startup_dashboard_state,
)
from src.web.dashboard_views import render_detail_page_from_snapshot


WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_FILE = WEB_DIR / "templates" / "dashboard.html"


def flight_detail(flight_id: str) -> HTMLResponse:
    snapshot = get_flight_detail_snapshot_cached(flight_id)
    return render_detail_page_from_snapshot(snapshot)


def plane_detail(airplane_id: str) -> HTMLResponse:
    snapshot = get_plane_detail_snapshot_cached(airplane_id)
    return render_detail_page_from_snapshot(snapshot)


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


@app.websocket("/ws/clock")
async def clock_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    dashboard_state.clock_clients.add(websocket)

    try:
        if dashboard_state.latest_clock:
            await websocket.send_json({"kind": "sync", "clock": dashboard_state.latest_clock})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        dashboard_state.clock_clients.discard(websocket)


@app.websocket("/ws/window-flights")
async def window_flights_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    dashboard_state.window_clients.add(websocket)

    try:
        await websocket.send_json({"kind": "snapshot", "window": dashboard_state.latest_window})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        dashboard_state.window_clients.discard(websocket)

@app.get("/api/status")
def status() -> dict[str, object]:
    return {
        "database_ok": True,
        "window_rows": len(read_window_flights_snapshot()["rows"]),
    }

@app.on_event("startup")
async def startup_dashboard() -> None:
    await startup_dashboard_state()


@app.on_event("shutdown")
async def shutdown_dashboard() -> None:
    await shutdown_dashboard_state()


@app.get("/api/flight/{flight_id}")
def flight_detail_api(flight_id: str) -> dict[str, object]:
    return get_flight_detail_snapshot_cached(flight_id)


@app.get("/api/plane/{airplane_id}")
def plane_detail_api(airplane_id: str) -> dict[str, object]:
    return get_plane_detail_snapshot_cached(airplane_id)
