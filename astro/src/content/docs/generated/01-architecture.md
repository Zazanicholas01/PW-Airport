---
title: Architecture
---

# Architecture

This topic is derived from `../../../README.md` (“Macro Architecture” + workflows) and the subsystem guides in `src/<module>/README.md`.

## Main components

- `../../server.py`: process entrypoint; initializes shared state (`PrefabStore`, `InitGraph`, `WorldState`) and starts WebSocket server.
- `../../transport/ws_server.py`: orchestrates setup flow, runtime flow, schedulers, clock sync, and command dispatch to Unity.
- `../../transport/message_bus.py`: async in/out queues between WebSocket transport and backend logic.
- `../../handlers/setup_bus.py`: Unity bootstrap payloads (splines + prefabs), builds paths, writes `Percorso`.
- `../../handlers/runtime_bus.py`: runtime Unity events (`path_completed`, `plane_left_stand`) and disembark timers.
- `../../schedulers/spawn_scheduler.py`: initial parked-plane spawns after setup.
- `../../schedulers/flight_scheduler.py`: sliding-window decision engine for departures/arrivals lifecycle.
- `../../services/flight_generator.py`: creates randomized flights in DB.
- `../../db/db_functions.py`: domain-level DB transitions (assign, reserve, status changes).
- `../../domain/sim_clock.py`: authoritative simulation clock (`time_scale`, pause/fast-forward).
- `../../web/dashboard_app.py` + `../../web/static/`: dashboard APIs + live UI.
- `../../../Unity_Scripts/`: Unity websocket client, spline export/import, spawning, movement, time controls.

## Layering (mental model)

- Transport (`../../transport/`): session lifecycle, message IO, clock sync, task orchestration
- Handlers (`../../handlers/`): decode/route Unity payload effects into domain + DB transitions
- Schedulers (`../../schedulers/`): decide *when* to spawn / move planes and advance flights
- DB (`../../db/`): models + state transitions + queries (sliding window)
- Domain (`../../domain/`): in-memory stores and authoritative clock
- Web (`../../web/`): read-only monitoring of DB + event log

## Data model (high level)

Core entities in `../../db/models.py`:

- `Flight` (`Viaggio`): schedule + operational status
- `Airplane` (`Aereo`): aircraft state and current route
- `Stand` (`Piazzola`): stand availability and linked airplane
- `Path` (`Percorso`): generated spline segments for movement

Schema creation/reset: `../../../scripts/init_db.py`  
Static seed: `../../../scripts/startup.py`
