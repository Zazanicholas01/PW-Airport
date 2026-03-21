# `src/handlers` Workflow Guide

This document describes the workflow of `src/handlers`, aligned with the architecture in `../../README.md`.

## Scope

The handlers layer processes decoded incoming Unity payloads after transport routing:

- Setup phase handler (`setup_bus.py`)
- Runtime phase handler (`runtime_bus.py`)

Handlers consume queue payloads and apply domain/database transitions.  
They are orchestrated by `src/transport/ws_server.py`.

## Files and Responsibilities

### `setup_bus.py`

Defines:

- `SetupState`: in-memory setup phase state machine.
- `SetupBusHandler`: async queue consumer for setup/import events.

Main responsibilities:

- Receive setup control events and batch payloads from Unity.
- Buffer spline and prefab payloads during their corresponding batch windows.
- Commit setup data to in-memory stores and DB:
  - feed spline data to `InitGraph`
  - feed prefab data to `PrefabStore`
  - update stand positions from spline first-knot coordinates
  - capture landing spawn position (`Spline_LongLanding` first knot)
- Build and persist generated paths into `Percorso`.
- Mark setup completion and block further setup payload processing.

### `runtime_bus.py`

Defines `RuntimeBusHandler`, async queue consumer for runtime Unity events.

Main responsibilities:

- Handle event payloads after setup is complete.
- React to `path_completed` and `plane_left_stand` events.
- Update DB state for airplane, flight, and stand lifecycle.
- Start and manage disembark timers in **simulation time** (aware of time scale).

## End-to-End Handler Workflow

### 1) Setup phase (`SetupBusHandler`)

Caller path:

`src/transport/ws_server.py` -> `incoming_dispatch_loop(...)` -> `setup_bus.enqueue(...)`

Flow:

1. Transport forwards payloads while `setup_completed == False`.
2. `SetupBusHandler` event loop consumes queued payloads.
3. Control events open/close batch windows:
   - `setup-init` -> reset setup state
   - `send-splines` / `finish-send-splines`
   - `send-prefabs` / `finish-send-prefabs`
4. During active windows:
   - spline payloads are buffered
   - prefab payload lists are buffered
5. On spline commit:
   - master spline is passed to `InitGraph.add_master_spline`
   - other splines to `InitGraph.add_spline`
   - stand positions are extracted and persisted
   - landing spawn position is captured
6. On prefab commit:
   - prefabs are added to `PrefabStore`
7. When both commits are done:
   - `InitGraph.build_paths()` is executed
   - existing `Path` rows are replaced safely:
     - clear `Airplane.route_id` / `Vehicle.route_id`
     - delete all `Path` rows
     - reset `Path` sequence
     - insert rebuilt paths
   - marks:
     - `state.setup_completed = True`
     - `setup_completed = True`

Outcome:

- System transitions from setup/import mode to runtime mode with usable prefabs, paths, and positions.

### 2) Runtime phase (`RuntimeBusHandler`)

Caller path:

`src/transport/ws_server.py` -> `incoming_dispatch_loop(...)` -> `runtime_bus.enqueue(...)`

Flow:

1. Transport forwards payloads after setup completion.
2. `RuntimeBusHandler` event loop consumes queued payloads.
3. Only `type="event"` with valid `airplane_id` are processed.

### Runtime events and effects

- `path_completed`
  - Load airplane and current route.
  - If route destination is `Departure`: log and return (no disembark flow).
  - Else (landing path completed):
    - airplane status -> `Disembarking`
    - latest landing/disembarking flight status -> `Disembarking`
    - linked stand status -> `Occupied`
    - start disembark timer task for this airplane.

- `plane_left_stand`
  - Resolve stand by airplane link.
  - If consistent link exists:
    - unlink stand airplane
    - stand status -> `Available`

### Disembark timer workflow

`_start_disembark_timer()` ensures one active timer per airplane:

- cancels previous timer for same airplane (if any)
- starts `_finish_disembark(airplane_id)` task

`_finish_disembark(...)`:

1. Sleeps `DISEMBARK_SIM_SECONDS` (default 5 min) in **simulated time**.
2. On wake:
   - if airplane still `Disembarking`, set `Parked`
   - mark latest associated flight as `Completed` (if still in landing/disembarking statuses)
3. Commit transaction.

Simulation-time sleep (`_sleep_sim_seconds`) adapts to:

- current clock time scale
- pause/fast-forward behavior
- shared `clock_changed` wake event

## Queue and Concurrency Model

Both handlers have the same queue pattern:

- `enqueue(payload)` pushes payload into an internal `asyncio.Queue`.
- `start()` creates one consumer task (`_event_loop`).
- Loop processes payloads sequentially.
- `stop()` cancels consumer task (setup handler has explicit stop).

Runtime handler additionally manages per-airplane timer tasks in `_disembark_tasks`.

## Integration with Other Layers

### Setup handler integrates with

- `src/domain/prefab_store.py`
- `src/init_graph.py`
- `src/db/models.py` and SQLAlchemy session
- `schema_nodi.json` (indirectly through `InitGraph`)

### Runtime handler integrates with

- `src/domain/sim_clock.py` (via injected clock in transport)
- `src/db/models.py` and SQLAlchemy session
- transport wake/sync primitives (`clock_lock`, `clock_changed`)

### Transport routing boundary

`src/transport/ws_server.py` is responsible for selecting active handler:

- before setup finished -> setup handler
- after setup finished -> runtime handler

Handlers assume payloads are already decoded JSON objects by `WsMessageBus`.

## Important Caveats

- Setup payloads are ignored once `state.setup_completed` is set.
- Path rebuild on setup intentionally replaces all existing path rows.
- Runtime event handling is conservative: invalid/missing IDs or mismatched relations are ignored safely.
- Disembark completion depends on simulated clock progression (pause can freeze timer completion).
