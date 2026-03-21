# Troubleshooting

## Docker stack issues

- Check health and one-shot jobs: `docker compose ps`
- Tail logs: `docker compose logs -f --tail=200`

Common causes:

- Postgres not healthy yet (wait for `pg_isready` healthcheck).
- Metabase setup job needs time (it waits for `/api/health`).

## “Nothing happens” after starting the Python server

The backend depends on Unity sending setup data (splines + prefabs). Until setup completes:

- paths (`Path`/`Percorso`) are not generated
- schedulers may have nothing actionable to do

See:

- Setup handshake: `../03-end-to-end-workflows/README.md`
- Setup handler: `../../handlers/setup_bus.py`

## Resetting simulation data

- Schema reset: `../../../scripts/init_db.py` (also run by `airportdb-init` in Compose)
- Seed/bootstrap: `../../../scripts/startup.py`
