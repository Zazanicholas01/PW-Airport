# `src/db` Workflow Guide

This document describes the database layer in `src/db`, aligned with the architecture in `../../README.md`.

## Scope

`src/db` provides:

- SQLAlchemy engine/session bootstrap
- ORM model mapping for airport simulation entities
- DB helper functions used by schedulers, handlers, transport, and web APIs

The DB layer centralizes persistence logic and state transitions for flights, airplanes, stands, and paths.

## Files and Responsibilities

### `engine.py`

Database bootstrap utilities.

Responsibilities:

- Build connection URL from env vars (`DATABASE_URL` or `POSTGRES_*` fallback).
- Create and cache SQLAlchemy engine (`get_engine()`).
- Provide simple session-yield helper (`get_db(Session)`).

Default fallback URL shape:

`postgresql+psycopg://airport:airport@localhost:5432/Airport`

### `models.py`

SQLAlchemy ORM definitions for all core entities.

Important design rule:

- Python model names are English (`Flight`, `Airplane`, ...).
- DB table/column names are Italian (`Viaggio`, `Aereo`, ...), matching schema scripts.

Core operational models:

- `Flight` (`Viaggio`)
- `Airplane` (`Aereo`)
- `Stand` (`Piazzola`)
- `Path` (`Percorso`)

Support models:

- `Airport`, `Airline`, `Terminal`, `Vehicle`, `Operation`, `Passenger`, `Cargo`, `ParkingSpot`

### `db_functions.py`

Domain-level DB operations and query helpers.

Main groups:

- Lookup helpers:
  - `get_airplane_prefab`
  - `list_flights_in_sliding_window`
- Link helpers:
  - `link_airplane_to_stand`
  - `unlink_airplane_from_stand`
- Normalization helpers:
  - `normalize_flight_type`
  - `normalize_distance`
  - `stand_category`
- Lifecycle transitions:
  - departure assignment
  - inbound airplane creation
  - stand reservation
  - path assignment
  - landing departure state shift

## End-to-End DB Workflows

### 1) Setup persistence workflow

Caller path:

`src/handlers/setup_bus.py` (uses models + Session directly from `get_engine`)

Flow:

1. Stand positions extracted from spline payloads are persisted to `Stand.position`.
2. Path rebuild sequence:
   - clear `Airplane.route_id` / `Vehicle.route_id`
   - delete all existing `Path` rows
   - reset `Path` identity sequence
   - insert rebuilt path rows

Outcome:

- DB reflects the latest Unity-exported topology and movement routes.

### 2) Sliding window query workflow

Caller path:

- `src/transport/ws_server.py` flight scheduler loop
- `src/web/dashboard_app.py` API `/api/window`

Function:

- `list_flights_in_sliding_window(airport_icao, now_utc, window)`

Query behavior:

- Collects multiple flight sets to support lifecycle visibility:
  - unscheduled departures/arrivals in window
  - scheduled departures/arrivals with assigned airplane
  - active inbound flights (`Landing`, `Lan_Ongoing`, `Disembarking`)

Outcome:

- Single merged list used by scheduling decisions and dashboard display.

### 3) Departure allocation workflow

Functions:

- `assign_airplane_to_departure_flight(...)`
- `assign_path_to_airplane(...)`

Flow:

1. Select compatible parked airplane (type + range match when available).
2. Set airplane status to `Reserved` and attach airline code.
3. Set flight `airplane_id` + status `Scheduled`.
4. Assign route from stand source to `Departure`.

Outcome:

- Flight is scheduled with a concrete plane and departure path.

### 4) Inbound (arrival) preparation workflow

Functions:

- `create_and_assign_airplane_for_landing_departure(...)`
- `mark_landing_departed(...)`
- `reserve_stand_and_link_airplane_for_landing_arrival(...)`
- `assign_landing_path_for_airplane(...)`

Flow:

1. Create airplane for unscheduled inbound flight (optional prefab-guided type/range).
2. Link airplane to flight; set flight to `Scheduled`.
3. At departure time from remote airport:
   - `mark_landing_departed` sets flight `Dep_Ongoing`, airplane `InFlight`.
4. Near arrival:
   - reserve compatible stand
   - link stand to airplane
   - set flight `Landing`, airplane `Reserved`
   - assign landing path based on airplane range (`Short/Medium/LongLanding -> stand`)

Outcome:

- Inbound flight transitions from planned to runway/stand-ready state.

### 5) Stand link workflow

Functions:

- `link_airplane_to_stand(...)`
- `unlink_airplane_from_stand(...)`

Current usage:

- Transport spawn hook links bootstrap spawns to stands.
- Runtime events can later clear stand links when planes leave.

## Function Map (Quick Reference)

- Read/query:
  - `get_airplane_prefab`
  - `list_flights_in_sliding_window`
- Normalize:
  - `normalize_flight_type`
  - `normalize_distance`
  - `stand_category`
- Reserve/assign:
  - `reserve_stand_for_arrival_flight`
  - `assign_airplane_to_departure_flight`
  - `create_and_assign_airplane_for_landing_departure`
  - `reserve_stand_and_link_airplane_for_landing_arrival`
  - `assign_path_to_airplane`
  - `assign_landing_path_for_airplane`
- State transitions:
  - `mark_landing_departed`
- Stand links:
  - `link_airplane_to_stand`
  - `unlink_airplane_from_stand`

## Schema and Seed Relationship

While not inside `src/db`, these scripts define/populate the schema used by this package:

- `scripts/init_db.py`: recreate DB and apply schema DDL.
- `scripts/startup.py`: seed airports, airlines, terminals, stands, parking spots, and vehicles.

`models.py` is expected to stay aligned with that schema.

## Integration with Other Layers

- `src/transport/ws_server.py`
  - calls query + lifecycle helpers in scheduling loop
- `src/handlers/setup_bus.py`
  - writes setup-derived positions and rebuilt paths
- `src/handlers/runtime_bus.py`
  - updates statuses at runtime using ORM session operations
- `src/services/*`
  - generator/provisioning services create or enrich rows consumed by scheduler transitions
- `src/web/dashboard_app.py`
  - reads flights/planes for dashboard APIs

## Important Caveats

- Helper functions usually commit internally; coordinate call ordering carefully at orchestration layer.
- `list_flights_in_sliding_window` intentionally merges several status subsets, so callers should treat result as operational feed, not a strict SQL "single state" view.
- Path assignment functions return `None` on missing route; callers must handle this.
- Vocabulary normalization is permissive (legacy Italian/variant strings are mapped to canonical values when possible).

## Typical Usage

### Engine and session

```python
from sqlalchemy.orm import sessionmaker
from src.db.engine import get_engine

Session = sessionmaker(bind=get_engine(), future=True)
```

### Departure assignment

```python
from src.db.db_functions import assign_airplane_to_departure_flight, assign_path_to_airplane

result = assign_airplane_to_departure_flight(flight_id=flight_id, required_type="Passengers")
if result:
    airplane_id, stand_id = result
    assign_path_to_airplane(airplane_id=airplane_id, source=stand_id, destination="Departure")
```
