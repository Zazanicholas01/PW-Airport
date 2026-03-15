# `src/web` Workflow Guide

The dashboard web layer is in reset mode. The previous client runtime, projection layer, and event bridge were removed so the UI can be rebuilt from a clean baseline while keeping the existing visual style.

## Current scope

- Serve the dashboard shell from `templates/dashboard.html`
- Serve static styling and assets from `static/`
- Preserve the existing layout/theme as a rebuild baseline

## Key files

### `dashboard_app.py`

Minimal FastAPI app that:

- serves `/`
- mounts `/static`

### `templates/dashboard.html`

Static dashboard markup extracted from the old JS-rendered schedule screen.

### `static/dashboard.css`

Preserved theme, layout, board, table, log, and responsive styling.

## Run

From repository root:

```bash
uvicorn src.web.dashboard_app:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## Notes

- `__init__.py` is intentionally empty.
- No dashboard APIs are exposed right now.
- No dashboard client runtime is loaded right now.
- Rebuild work should start from the static HTML/CSS baseline.
