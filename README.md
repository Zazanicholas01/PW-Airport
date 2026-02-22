# PW-Airport

Real-time airport simulation with:

- Python backend (authoritative scheduling, DB state, and simulation clock)
- Unity client (scene setup, prefab spawning, spline movement)
- PostgreSQL + Metabase (data persistence and analytics)
- FastAPI dashboard (flight window, planes, and live logs)

## Macro Architecture

### Main components

- `src/server.py`: process entrypoint; initializes shared state (`PrefabStore`, `InitGraph`, `WorldState`) and starts WebSocket server.
- `src/transport/ws_server.py`: orchestrator for setup flow, runtime flow, schedulers, clock sync, and command dispatch to Unity.
- `src/transport/message_bus.py`: async in/out queues between WebSocket transport and backend logic.
- `src/handlers/setup_bus.py`: handles Unity bootstrap payloads (splines + prefabs), builds paths, writes `Percorso` table.
- `src/handlers/runtime_bus.py`: handles runtime Unity events (`path_completed`, `plane_left_stand`) and disembark timers.
- `src/schedulers/spawn_scheduler.py`: plans initial parked-plane spawns after setup.
- `src/schedulers/flight_scheduler.py`: sliding-window decision engine for departures/arrivals lifecycle.
- `src/services/flight_generator.py`: creates random flights in DB for simulation.
- `src/db/db_functions.py`: domain-level DB transitions (assign planes, reserve stands, assign paths, status transitions).
- `src/domain/sim_clock.py`: authoritative simulation clock with adjustable `time_scale`.
- `src/web/dashboard_app.py` + `src/web/static/*`: dashboard APIs + live UI.
- `Unity_Scripts/*`: Unity side websocket client, dispatchers, spline export/import, spawning, path-follow movement, time controls.

### Data model (high level)

Core entities in `src/db/models.py`:

- `Flight` (`Viaggio`): schedule + operational status.
- `Airplane` (`Aereo`): aircraft state and current route.
- `Stand` (`Piazzola`): parking/stand availability and optional linked airplane.
- `Path` (`Percorso`): generated spline segments for movement.
- Supporting: `Airport`, `Airline`, `Terminal`, `Vehicle`, `Operation`, `Passenger`, `Cargo`, `ParkingSpot`.

Schema creation/reset: `scripts/init_db.py`  
Seed static data (airports, airlines, terminals, stands, parking, vehicles): `scripts/startup.py`

## End-to-End Workflows

### 1) Startup and setup handshake (Unity -> Python)

1. Unity connects to `ws://localhost:8765` (`UnityWSClient.cs`).
2. Unity `SplineRegistry` sends control + spline batch:
   - `setup-init`
   - `send-splines`
   - many spline payloads (including `MasterSpline`)
   - `finish-send-splines`
3. Unity `PrefabRegistry` waits for spline send completion, then sends:
   - `send-prefabs`
   - prefab list
   - `finish-send-prefabs`
4. Python `SetupBusHandler`:
   - buffers spline/prefab batches
   - stores prefabs in `PrefabStore`
   - stores stand positions + landing spawn reference from splines
   - builds full landing/departure paths via `InitGraph`
   - wipes/rebuilds `Percorso` in DB
   - marks setup complete (`setup_finished=True`)

Result: backend has prefabs, stand coordinates, and generated movement routes persisted.

### 2) Path generation logic (macro)

`src/init_graph.py` does:

- Load node-link schema from `schema_nodi.json`.
- Parse master spline knots to compute normalized `t` intervals along `MasterSpline`.
- Build landing paths:
  - `LandingSpline -> MasterSpline slice -> StandSpline (reverse)`
- Build departure paths:
  - `StandSpline -> MasterSpline slice -> Spline_Departure`
- Emit path records with `{source, destination, segments[]}` and store in DB.

### 3) Initial spawn bootstrap

When setup is complete:

- `schedule_initial_spawns()` runs `SpawnScheduler.plan_initial_spawns()`.
- Scheduler resets stands + airplane-linked tables for clean bootstrap.
- Picks available stands and random plane prefabs.
- Emits `spawn_plane` commands with generated `airplane_id`.
- Outgoing hook in `ws_server.py`:
  - ensures airplane row exists (`ensure_airplane_row`)
  - links stand -> airplane for bootstrap spawns
  - records in-memory world snapshot (`WorldState`)

### 4) Flight lifecycle scheduling (authoritative in Python)

`flight_scheduler_loop()` in `src/transport/ws_server.py`:

- waits for setup completion
- generates initial random flights (`RandomFlightGenerator.generate_flights`)
- every poll:
  - reads simulation time from `SimulationClock`
  - gets flights in sliding window (`list_flights_in_sliding_window`)
  - applies `FlightSlidingWindowScheduler` stage guards

Lifecycle decisions:

- Departure scheduling:
  - assign parked compatible airplane (`assign_airplane_to_departure_flight`)
  - assign stand->Departure path (`assign_path_to_airplane`)
- Inbound flight preparation:
  - create/link airplane for inbound flight (`create_and_assign_airplane_for_landing_departure`)
  - mark departed -> `Ongoing` (`mark_landing_departed`)
- Arrival reservation:
  - reserve compatible stand + link airplane (`reserve_stand_and_link_airplane_for_landing_arrival`)
  - assign landing path based on airplane range (`assign_landing_path_for_airplane`)
- Movement commands:
  - send `start_path` for departures at departure time
  - spawn inbound plane near landing shortly before arrival
  - send `start_path` for landing approach

### 5) Runtime event handling (Unity -> Python)

Unity emits events:

- `path_completed` (from `PathCompletionReporter`)
- `plane_left_stand` (event consumed by runtime handler)

`RuntimeBusHandler` updates DB state:

- On landing path completion:
  - airplane `Disembarking`
  - flight `Disembarking`
  - stand `Occupied`
  - starts simulated disembark timer
- After timer expiration:
  - airplane `Parked`
  - flight `Completed`
- On `plane_left_stand`:
  - stand unlinked and reset `Available`

### 6) Simulation clock and time control

- Python `SimulationClock` is authoritative.
- `clock_sync_loop()` pushes `clock_sync` events to Unity (10 Hz).
- Unity consumes sync (`SimClockClient`, `SimTimeLabel`).
- Unity UI controls (`SimTimeControls`) send:
  - `set_time_scale`
  - optionally `set_sim_time`
- `handle_clock_control()` applies changes and wakes scheduling loops.

### 7) Dashboard workflow

FastAPI app (`src/web/dashboard_app.py`) exposes:

- `GET /api/window`: flights in sliding window
- `GET /api/planes`: planes + stand + route snapshot
- `GET /api/flight/{id}`: single flight lookup
- `WS /ws/events`: tails JSONL event stream

Frontend (`dashboard.js`) provides:

- auto-refresh from clock/events + timers
- list view for flights and planes
- detail routes (`#plane/:id`, `#flight/:id`)
- progress visualization and completed-flight banner

## Message Contracts (primary)

### Unity -> Python

- Setup control events: `setup-init`, `send-splines`, `finish-send-splines`, `send-prefabs`, `finish-send-prefabs`
- Spline payload: `{ "type":"event", "event":"spline", "spline": {...} }`
- Runtime events: `path_completed`, `plane_left_stand`
- Time commands: `set_time_scale`, `set_sim_time`

### Python -> Unity

- `spawn_plane`
- `start_path` with ordered spline segments
- `clock_sync`
- initial `welcome`

## Status / vocabulary conventions

Canonical values are documented in `standard_vocabulary.txt` and used across code:

- Flight statuses: `Unscheduled`, `Scheduled`, `Ongoing`, `Landing`, `Disembarking`, `Completed`, `StandReserved`
- Airplane statuses: `Parked`, `Reserved`, `InFlight`, `Disembarking`
- Stand statuses: `Available`, `Reserved`, `Occupied`
- Flight types: `Cargo`, `Passengers`
- Range: `Short`, `Medium`, `Long`

## Local run / services

### Infra stack

```bash
docker compose up -d
```

Services:

- Postgres: `localhost:5432`
- Metabase: `http://localhost:3000`
- Metabase DB URI: `postgresql://airport:airport@postgres:5432/Airport`

### Python server

```bash
python -m src.server
```

### Dashboard

```bash
uvicorn src.web.dashboard_app:app --reload --host 0.0.0.0 --port 8000
```
