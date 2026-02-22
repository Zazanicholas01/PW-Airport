# `src/services` Workflow Guide

This document describes the workflow of `src/services`, aligned with the architecture in `../../README.md`.

## Scope

The `services` layer contains reusable domain services that support scheduling and transport flows:

- Flight dataset generation for simulation (`flight_generator.py`)
- Airplane row provisioning during spawn commands (`spawn_tracking.py`)

These services are called by orchestration layers (`src/transport`, `src/schedulers`) and DB helpers (`src/db`).

## Files and Responsibilities

### `flight_generator.py`

Defines `RandomFlightGenerator`, responsible for creating randomized `Flight` rows (`Viaggio`) for the simulation.

Main responsibilities:

- Load required metadata from DB (`Airport`, `Terminal`, `Airline`).
- Build compatible flight attributes:
  - direction (departure from `LIAG` or arrival to `LIAG`)
  - `tipo` (`Cargo` / `Passengers`)
  - airline chosen by route category and type
  - terminal compatible with flight type
  - departure/arrival timestamps inside a scheduling window
- Generate ICAO-like identifiers with per-airline sequence counters.
- Insert generated flights and commit.

### `spawn_tracking.py`

Defines `ensure_airplane_row(...)`, used when sending `spawn_plane` commands.

Main responsibilities:

- If `airplane_id` already exists in DB, reuse it.
- If missing, generate UUID and create `Airplane` row.
- Derive airplane `type` and `range` from prefab name via `src.utils.mapping`.
- Fallback to defaults (`Passengers`, `Medium`) for unknown prefabs.

## End-to-End Service Workflows

### 1) Airplane provisioning on spawn (`ensure_airplane_row`)

Caller path (current architecture):

`src/transport/ws_server.py` outgoing hook (`_track_spawns`) -> `ensure_airplane_row(...)`

Flow:

1. Receive `airplane_id` (optional) and `prefab`.
2. Open DB session.
3. If `airplane_id` exists and row is present: return same ID.
4. Else create a new `Airplane` row:
   - model from `prefab`
   - type/range from mapping
   - status initialized as `Parked`
   - default numeric values for speed/fuel/capacity
5. Commit and return resolved `airplane_id`.

Outcome:

- Transport layer can safely link stand/world state to a guaranteed DB airplane row.

### 2) Random flight generation (`RandomFlightGenerator.generate_flights`)

Caller path (current architecture):

`src/transport/ws_server.py` -> `flight_scheduler_loop(...)` -> `RandomFlightGenerator(...).generate_flights(...)`

Flow:

1. Validate input `n`.
2. **Reset flights table** by deleting existing `Flight` rows.
3. Load metadata:
   - remote airports (`icao != LIAG`)
   - terminals
   - allowed airlines (`LUN`, `UMB`, `JAE`, `ALI`)
4. Build parked airplane compatibility pairs (`type`, `range`) for first-departure compatibility logic.
5. Initialize per-airline flight number counters from existing ICAO strings.
6. For each flight:
   - choose direction and remote airport
   - choose type and compatible terminal
   - classify route category (`National`, `European`, `International`)
   - pick airline constrained by type + category
   - compute departure/arrival times (window-aware)
   - build flight code and create `models.Flight`
7. Persist all generated rows in one transaction.

Outcome:

- Returns the created `Flight` objects and updates DB with a new randomized scenario.

## Timing and Window Logic

`RandomFlightGenerator` provides two time strategies:

- `_times_departure_within_window(...)`: selects departure within window and arrival after random duration.
- `_times_arrival_within_window(...)`: selects arrival within window and infers a valid earlier departure.

`ensure_in_window=True` enables debug-oriented behavior:

- First generated flight forced as departure from `LIAG`.
- Second forced as arrival to `LIAG`.

This is used to quickly exercise both scheduler branches.

## Data and Business Constraints

### Flight generation constraints

- Requires seeded `Airport`, `Terminal`, and `Airline` data.
- Airline selection is filtered by:
  - flight type compatibility
  - nationality class vs route category
- Terminal selection prefers matching terminal type (`Passengers`/`Cargo`) with fallback to any terminal.

### Spawn provisioning constraints

- Prefab name must match `src.utils.mapping` to get exact `type`/`range`.
- Unknown prefab names are accepted with safe defaults.

## Important Caveats

- `generate_flights(...)` currently deletes all rows in `Flight` before generating new ones.
  - Treat as simulation reset behavior, not incremental scheduling.
- `RandomFlightGenerator` is random by default; inject a custom `rng` for deterministic tests.
- Airline codes for generation are restricted to `ALLOWED_AIRLINES`.

## Integration with Other Layers

- `src/transport/ws_server.py`
  - calls `RandomFlightGenerator` in flight scheduler startup
  - calls `ensure_airplane_row` in outgoing spawn hook
- `src/schedulers/flight_scheduler.py`
  - consumes generated flights via sliding-window rules
- `src/db/db_functions.py`
  - performs later lifecycle transitions for generated/provisioned records

## Typical Usage

### Generate flights

```python
from sqlalchemy.orm import sessionmaker
from src.db.engine import get_engine
from src.services.flight_generator import RandomFlightGenerator

Session = sessionmaker(bind=get_engine(), future=True)
flights = RandomFlightGenerator(Session).generate_flights(20, ensure_in_window=True)
```

### Ensure airplane exists for a spawn

```python
from src.services.spawn_tracking import ensure_airplane_row

airplane_id = ensure_airplane_row(airplane_id=None, prefab="a320")
```
