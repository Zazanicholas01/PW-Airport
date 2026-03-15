# `src/web` Workflow Guide

This document describes the workflow of the web layer located in `src/web`, aligned with the project-level architecture in `../../README.md`.

## Scope

This folder contains the dashboard UI and APIs used to inspect simulation state in near real-time:

- Flight scheduling window
- Plane/stand/route snapshots
- Live event stream (logs + clock ticks)
- Client-side detail pages for planes and flights

## Files and Responsibilities

### `dashboard_app.py`

FastAPI application for serving the dashboard and data endpoints.

- Serves static assets from `/static` and HTML from `/`.
- Exposes API routes:
  - `GET /api/dashboard`: returns the full dashboard snapshot for one airport/window.
  - `GET /api/stream`: SSE stream for clock, log, heartbeat, and snapshot events.
  - `GET /api/flight/{flight_id}`: returns one flight (by DB `id` or by `icao`).
  - `GET /api/planes`: returns planes enriched with stand and path info.
- Maintains the dashboard-facing clock cache and snapshot builder.
- Bridges backend observer traffic into SSE events for the browser.

### `templates/dashboard.html`

Initial HTML shell with:

- dashboard app mount point
- `/static/dashboard.css`
- `/static/dashboard.js`

### `static/dashboard.js`

Main client-side bootstrap.

- Creates store, API service, SSE event service, refresh fallback service, and router.
- Starts the realtime stream and initial route handling.

### `static/app/services/events.js`

Realtime SSE consumer.

- Connects to `/api/stream`.
- Handles:
  - `snapshot`
  - `clock`
  - `log`
  - `heartbeat`
- Updates store connection status and dashboard state.

### `static/app/services/refresh.js`

HTTP fallback refresh layer.

- Fetches `/api/dashboard` manually when needed.
- No polling loop; SSE is the primary transport.

### `static/dashboard.css`

Visual styling for:

- Overall layout and panel
- Tables and pills
- Live log viewer (`#events`, `.logline`)
- Flight progress bar and completion banner
- Responsive plane/flight detail layout

## End-to-End Web Workflow

### 1) Page load

1. Browser requests `GET /`.
2. FastAPI serves `templates/dashboard.html`.
3. Browser loads `dashboard.css` and `dashboard.js`.

### 2) Initial hydration

On startup, JS executes:

- `events.connect()` -> `GET /api/stream` via `EventSource`
- `router.start()`
- optional HTTP fallback refresh if needed

### 3) Realtime updates

- Backend appends JSON lines into `events.jsonl`.
- `dashboard_app.py` receives observer traffic from the backend websocket.
- The dashboard server pushes SSE events to browser clients:
  - `clock`
  - `log`
  - `snapshot`
  - `heartbeat`
- The browser updates store state directly from the SSE stream.

### 4) User navigation

- Clicking a flight row sets `location.hash = #flight/<id>`.
- Clicking a plane row sets `location.hash = #plane/<id>`.
- Router renders detail pages from cache, with API fallback when missing.

### 5) Data transformations

Server side:

- `_flight_to_dict()` normalizes SQLAlchemy rows into JSON-safe fields.
- `_build_dashboard_snapshot()` computes the enriched dashboard payload.
- Clock and progress are derived on the backend before being pushed to the UI.

Client side:

- Converts ISO strings to local display time.
- Renders human-readable event rows.
- Uses backend-provided snapshot state as the primary source of truth.

## Integration with Root Architecture

Per `../../README.md`, this web module is read-only monitoring for the authoritative simulation logic running in:

- `src/transport/ws_server.py`
- `src/handlers/*`
- `src/schedulers/*`
- `src/utils/event_log.py`

The dashboard does not mutate simulation state; it observes DB state plus backend event output.

## Run

From repository root:

```bash
uvicorn src.web.dashboard_app:app --host 0.0.0.0 --port 8000
```

Then open:

- `http://localhost:8000`

## Notes

- `__init__.py` is intentionally empty (package marker).
- SSE is now the primary dashboard transport.
- `/api/dashboard` remains useful as a manual refresh and debugging endpoint.
- `api_flight` supports both DB `id` and `icao` to match UI route keys.
