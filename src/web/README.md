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
  - `GET /api/window`: returns flights inside a time window (default airport `LIAG`, default 60 min).
  - `GET /api/flight/{flight_id}`: returns one flight (by DB `id` or by `icao`).
  - `GET /api/planes`: returns planes enriched with stand and path info.
- Exposes realtime route:
  - `WS /ws/events`: tails `events.jsonl` and pushes lines to browser clients.
- Pulls data from:
  - `src.db.db_functions.list_flights_in_sliding_window`
  - SQLAlchemy models (`Flight`, `Airplane`, `Stand`, `Path`)
  - event log path from `src.utils.event_log.log_dir`.

### `templates/dashboard.html`

Initial HTML shell with:

- List view containers for flights, planes, live events.
- Base inputs (`airport`, `window`) and refresh button.
- Predefined plane detail view container.
- Includes:
  - `/static/dashboard.css`
  - `/static/dashboard.js`

### `static/dashboard.js`

Main client-side controller for data fetch, routing, rendering, and live updates.

- Data fetch and cache:
  - Fetches `/api/window`, `/api/planes`, and `/api/flight/{id}`.
  - Maintains `flightById` and `planeById` maps.
- UI routing:
  - Hash routes: `#plane/<id>`, `#flight/<id>`, list fallback.
  - Dynamically creates missing detail views (`plane_view`, `flight_view`) if needed.
- Auto-refresh behavior:
  - Timers (`10s` flights, `2s` planes).
  - Event-driven refresh debounce via `scheduleRefreshSoon()`.
- Live websocket consumer:
  - Connects to `/ws/events`.
  - Handles `clock` events to update simulated current time (`simNowMs`) and trigger refresh.
  - Renders log/event rows for non-clock events.
- Detail rendering:
  - Plane detail (status, stand, route, image by model).
  - Flight detail (status, schedule, progress bar, completion banner).

### `static/dashboard.css`

Visual styling for:

- Overall layout and panel.
- Tables and pills.
- Live log viewer (`#events`, `.logline`).
- Flight progress bar and completion banner.
- Responsive plane/flight detail layout.

### Static assets

- `static/background-airport.png`: page background image.
- `static/planes/models/*.png`: plane model images resolved by JS slug convention.
- `static/planes/_default.png`: fallback image.

## End-to-End Web Workflow

### 1) Page load

1. Browser requests `GET /`.
2. FastAPI serves `templates/dashboard.html`.
3. Browser loads `dashboard.css` and `dashboard.js`.

### 2) Initial data hydration

On startup, JS executes:

- `refreshWindow()` -> `GET /api/window`
- `refreshPlanes()` -> `GET /api/planes`
- `connectEvents()` -> `WS /ws/events`
- `ensurePlaneViews()` and `route()` for hash-aware rendering.

### 3) Realtime updates

- Backend appends JSON lines into `events.jsonl` (from server log hooks and clock loop).
- `WS /ws/events` tails new lines and streams them to browser.
- JS receives events:
  - if `type == "clock"`: updates simulation time reference, schedules quick refresh.
  - else: renders event row and schedules refresh.

### 4) User navigation

- Clicking a flight row sets `location.hash = #flight/<id>`.
- Clicking a plane row sets `location.hash = #plane/<id>`.
- Router renders detail pages from cache, with API fallback when missing.

### 5) Data transformations

Server side:

- `_flight_to_dict()` normalizes SQLAlchemy rows into JSON-safe fields.
- `_to_iso()` normalizes datetimes to UTC ISO strings.

Client side:

- Converts ISO strings to local display time.
- Computes minute deltas and progress bars from simulated clock (`simNowMs`).
- Resolves plane image URLs from `model` names.

## Integration with Root Architecture

Per `../../README.md`, this web module is read-only monitoring for the authoritative simulation logic running in:

- `src/transport/ws_server.py` (clock + scheduling + Unity commands)
- `src/handlers/*` and `src/schedulers/*`
- `src/utils/event_log.py` (event stream source consumed by `/ws/events`)

The dashboard does not mutate simulation state; it observes DB + event log outputs.

## Run

From repository root:

```bash
uvicorn src.web.dashboard_app:app --reload --host 0.0.0.0 --port 8000
```

Then open:

- `http://localhost:8000`

## Notes

- `__init__.py` is intentionally empty (package marker).
- `now_unix_ms` query support allows APIs to align with simulated time sent by backend clock events.
- `api_flight` supports both DB `id` and `icao` to match UI route keys.
