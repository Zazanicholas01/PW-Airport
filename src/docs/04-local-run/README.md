# Local run

## Prereqs

- Python 3.11+ recommended (Docker uses 3.11 images)
- Docker + Docker Compose (for Postgres + Metabase)

## Infra (Postgres + Metabase)

```bash
docker compose up -d
```

Services:

- Postgres: `localhost:5432` (DB: Airport; user/pass: airport)
- Metabase: http://localhost:3000

## Python server (WebSocket + schedulers)

```bash
python -m src.server
```

Notes:

- Backend listens for Unity on `ws://localhost:8765`.
- The setup phase must complete (splines + prefabs) before schedulers become meaningful.

## Dashboard (FastAPI)

```bash
uvicorn src.web.dashboard_app:app --reload --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.
