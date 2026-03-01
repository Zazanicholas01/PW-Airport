# Docker setup

This topic documents `../../../docker-compose.yml` and related init scripts.

## Services

### `postgres`

- Image: `postgres:16-alpine`
- Exposes: `5432:5432`
- Mounts:
  - `../../../docker/initdb/` into `/docker-entrypoint-initdb.d`
  - `postgres-data` volume for persistence

### `airportdb-init`

One-shot job that waits for Postgres healthcheck, then runs:

- `../../../scripts/init_db.py` (schema creation/reset)

### `metabase`

Metabase instance bound to `localhost:3000`, with its own internal DB in Postgres.

### `metabase-setup`

One-shot automation that:

- completes Metabase initial setup (if needed)
- sets reporting timezone
- provisions the “Airport DB” connection

### `airport-startup`

One-shot job that installs `../../../requirements.txt` and runs:

- `../../../scripts/startup.py` (seed static data + any bootstrap tasks)

## Logs volume

`../../../data/logs` is bind-mounted into the container at `/logs` and used via `LOG_DIR`.
