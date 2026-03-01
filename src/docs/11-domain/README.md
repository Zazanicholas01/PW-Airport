# Domain (simulation clock, world state, prefab store)

This topic is derived from `../../domain/README.md`.

## Prefab store

File: `../../domain/prefab_store.py`

- Stores prefab metadata sent by Unity during setup.
- Provides selection helpers for schedulers/spawn logic.

## Simulation clock

File: `../../domain/sim_clock.py`

- Backend is authoritative for simulation time.
- Supports `time_scale` control and pause/fast-forward semantics.
- Exposes clock sync payloads used by Unity (`clock_sync`) and the dashboard event stream.

## World state snapshot

File: `../../domain/world_state.py`

- Tracks in-memory snapshot of spawned planes and their linkage to stands/routes.
- Used as an operational cache alongside DB state.

## Next reads

- Full domain guide: `../../domain/README.md`
- Local run and time controls: `../04-local-run/README.md`

