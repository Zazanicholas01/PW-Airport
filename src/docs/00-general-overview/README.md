# General overview

PW-Airport is a real-time airport simulation with:

- Python backend: authoritative scheduling, DB state, simulation clock
- Unity client: scene setup, prefab spawning, spline movement
- PostgreSQL + Metabase: persistence and analytics
- FastAPI dashboard: read-only inspection (flights, planes, live logs)

## Key entrypoints

- Backend server entrypoint: `../../server.py`
- WebSocket orchestration: `../../transport/ws_server.py`
- Dashboard app: `../../web/dashboard_app.py`
- Unity scripts: `../../../Unity_Scripts`

## What “setup” means

At runtime, Unity “bootstraps” the backend by sending:

- spline definitions (including a `MasterSpline`)
- prefab catalog

The backend uses these to generate movement routes and persist them in the DB as `Path`/`Percorso` rows.

## Next reads

- Architecture: `../01-architecture/README.md`
- End-to-end workflows: `../03-end-to-end-workflows/README.md`
- Local run: `../04-local-run/README.md`

