# Dashboard / web

This topic is derived from `../../web/README.md`.

## Scope

The dashboard is read-only monitoring for the simulation:

- flight scheduling window
- planes/stands/routes snapshots
- live event stream (logs + clock ticks)

## Key files

- FastAPI app: `../../web/dashboard_app.py`
- HTML template: `../../web/templates/dashboard.html`
- Client JS: `../../web/static/dashboard.js`
- CSS: `../../web/static/dashboard.css`

## Run

```bash
uvicorn src.web.dashboard_app:app --reload --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

