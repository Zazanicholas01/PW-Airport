# `src/domain` Workflow Guide

This document describes the workflow of `src/domain`, aligned with the architecture in `../../README.md`.

## Scope

The domain layer contains in-memory core objects used by transport, handlers, and schedulers:

- Prefab selection/indexing (`prefab_store.py`)
- Authoritative simulation time model (`sim_clock.py`)
- Lightweight world snapshot for spawned planes (`world_state.py`)

These modules are framework-light and focused on domain behavior, not I/O orchestration.

## Files and Responsibilities

### `prefab_store.py`

Defines `PrefabStore`, an in-memory index of Unity prefab metadata.

Responsibilities:

- Store raw prefab payloads (`prefabs`) and lookup by name (`prefab_by_name`).
- Track plane-prefab uniqueness to avoid duplicate rotation pools.
- Build rotation pools (`deque`) for plane selection by:
  - `(type, range)` exact match
  - `type` fallback
  - `range` fallback
- Provide round-robin plane selection via `pick_plane_prefab(...)`.

Used by:

- Setup flow (`SetupBusHandler`) to ingest prefabs sent by Unity.
- Flight scheduling flow to choose compatible inbound plane prefab models.

### `sim_clock.py`

Defines `SimulationClock` and `ClockSync`.

Responsibilities:

- Keep authoritative simulation time based on:
  - monotonic real-time baseline
  - simulation baseline datetime
  - `time_scale`
- Support dynamic time controls:
  - `set_time_scale(...)`
  - `set_sim_time(...)`
- Produce sync payload objects (`make_sync`) for Unity/dashboard consumers.

Key property:

- `now()` is computed continuously from monotonic elapsed time, so simulation remains smooth between sync ticks.

### `world_state.py`

Defines:

- `Vec3`: safe conversion wrapper for `{x,y,z}` payloads.
- `PlaneOnStand`: typed snapshot model.
- `WorldState`: in-memory stand->plane registry.

Responsibilities:

- Record spawned planes by stand (`record_plane_spawn`).
- Keep first-known spawn metadata (prefab, position, timestamp).
- Provide snapshots for diagnostics (`to_dict`, `debug_summary`).

Behavior note:

- `record_plane_spawn` is idempotent per stand: if stand already has a plane recorded, existing entry is returned.

## End-to-End Domain Workflows

### 1) Prefab ingestion and selection

Caller path:

`src/handlers/setup_bus.py` -> `PrefabStore.add_prefabs(...)`

Flow:

1. Setup handler receives prefab list from Unity.
2. Each prefab is indexed by name.
3. Plane prefabs are classified through `src.utils.mapping` into canonical `type` and `range`.
4. Prefab names are inserted into round-robin deques.

Later usage:

`src/transport/ws_server.py` flight flow -> `PrefabStore.pick_plane_prefab(flight_type, required_range)`

Selection strategy:

1. exact `(type, range)`
2. `type` pool
3. `range` pool
4. any available plane pool

Each successful selection rotates the deque to distribute models across flights.

### 2) Simulation clock lifecycle

Caller path:

- transport session startup creates `SimulationClock`
- incoming time commands call `set_time_scale` / `set_sim_time`
- periodic sync loop calls `make_sync`

Flow:

1. Clock starts at `sim_start` (default: current UTC) with `time_scale=1`.
2. `now()` returns simulated time derived from monotonic elapsed real time.
3. Changing time scale preserves continuity by rebasing at current simulated timestamp.
4. Sync objects (`sync_id`, `sim_unix_ms`, `time_scale`) are sent to Unity and logged for dashboard updates.

### 3) Spawn world snapshot tracking

Caller path:

`src/transport/ws_server.py` outgoing hook (`_track_spawns`) -> `WorldState.record_plane_spawn(...)`

Flow:

1. On outgoing `spawn_plane`, transport passes stand/prefab/position.
2. Domain validates position payload and stores typed `Vec3`.
3. `WorldState` records one `PlaneOnStand` per stand.
4. Debug methods expose compact state summaries for observability.

## Data Contracts and Canonical Values

- Prefab classification relies on canonical mapping from `src/utils/mapping.py`.
- Simulation time values are UTC-aware datetimes and Unix milliseconds.
- Position payload contract is `{ "x": number, "y": number, "z": number }`.

## Integration with Other Layers

- `src/handlers/setup_bus.py`
  - populates `PrefabStore`
- `src/transport/ws_server.py`
  - creates and controls `SimulationClock`
  - records spawns in `WorldState`
- `src/schedulers/*` + `src/db/db_functions.py`
  - consume values derived from prefab and clock logic indirectly through transport orchestration
- `src/web/dashboard_app.py` / `src/web/static/dashboard.js`
  - consume clock events generated from `SimulationClock` syncs (via log stream)

## Important Caveats

- `PrefabStore` ignores unknown plane model names that cannot be mapped to type/range.
- `WorldState` currently tracks only stand-level spawn presence and initial metadata, not full trajectory history.
- `SimulationClock` requires timezone-aware datetimes for explicit `sim_start` and `set_sim_time(...)`.

## Typical Usage

### Prefab selection

```python
store.add_prefabs(prefab_payloads)
prefab_name = store.pick_plane_prefab("Cargo", "Long")
```

### Clock sync payload

```python
clock = SimulationClock()
sync = clock.make_sync()
# -> sync.sync_id, sync.sim_unix_ms, sync.time_scale
```

### World state snapshot

```python
state.record_plane_spawn(stand_id="P1", prefab="a320", position={"x":0,"y":0,"z":0})
snapshot = state.to_dict()
```
