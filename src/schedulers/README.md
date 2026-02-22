# `src/schedulers` Guide

This folder contains timing and eligibility logic for bootstrap spawns and flight lifecycle progression.

Schedulers decide when a step is allowed.
Schedulers do not directly send Unity commands or persist complex transitions; those side effects are executed by `src/transport/ws_server.py` and `src/db/db_functions.py`.

## Files

### `flight_scheduler.py`

Defines `FlightSlidingWindowScheduler`.

Core constants:

- `SLIDING_WINDOW = timedelta(hours=1)`
- `LANDING_NEAR_DELTA = timedelta(minutes=10)`

Core state:

- `airport_icao`: local airport used to classify departures vs arrivals.
- `window`: scheduling window (defaults to `SLIDING_WINDOW`).
- `handled`: in-memory one-shot guard keyed by `(flight_id, stage)`.
- `scheduled_flight_ids`: writable set exposed via `mark_scheduled()` (currently not used by the transport loop).

Core helpers:

- `_once(flight, stage)`: idempotency guard for repeated polling cycles.
- `_is_stage_eligible(...)`: shared predicate for side, status, UTC event time, optional airplane requirement, and optional `event_time <= now` checks.
- `_is_landing_near_ready(...)`: shared predicate for near-arrival landing actions (`status == "Landing"`, airplane linked, arrival within 10 minutes).

Stage gates exposed by the scheduler:

| Method | Expected side | Expected status | Time field / rule | One-shot key |
|---|---|---|---|---|
| `should_schedule_departure` | `origin == airport_icao` | `Unscheduled` | `departure_time` within `window` | `dep` |
| `should_assign_landing_plane` | `destination == airport_icao` | `Unscheduled` | `departure_time` within `window` | `landing_dep` |
| `should_mark_landing_departed` | `destination == airport_icao` | `Scheduled` | `departure_time <= now` | `landing_departed` |
| `should_reserve_landing_stand` | `destination == airport_icao` | `Ongoing` + airplane required | `arrival_time` within `window` | `landing_arr` |
| `should_start_departure_movement` | `origin == airport_icao` | `Scheduled` | `departure_time <= now` | `dep_start` |
| `should_spawn_landing_plane` | `destination == airport_icao` | `Landing` + airplane required | `arrival_time` within `LANDING_NEAR_DELTA` | `landing_spawn` |
| `should_start_landing_approach` | `destination == airport_icao` | `Landing` + airplane required | `arrival_time` within `LANDING_NEAR_DELTA` | `landing_start` |

### `spawn_scheduler.py`

Defines `SpawnScheduler`, used during simulation bootstrap to produce `spawn_plane` command payloads.

Main behavior:

1. `_reset_all_stands_once()` runs once per process and performs bootstrap cleanup.
2. `_ensure_stand_cache()` loads stand snapshot into memory.
3. `plan_initial_spawns()` samples free stands and plane prefabs, reserves each stand in DB, and returns command payloads.

Bootstrap cleanup in `_reset_all_stands_once()`:

- Sets all stands to `Available` and clears `stand.airplane_id`.
- Clears `flight.airplane_id`.
- Deletes all rows from `Operation`, `ParkingSpot`, and `Airplane`.

Output payload shape from `plan_initial_spawns()`:

- `command`: `"spawn_plane"`
- `prefab`: prefab name
- `stand_id`
- `position`
- `airplane_id`
- `spawn_context`: `"bootstrap"`

Default spawn batch size:

- `starting_n_prefabs = 3`

## Runtime Integration

`src/transport/ws_server.py` owns the execution loop and calls scheduler gates in sequence for each flight returned by `list_flights_in_sliding_window(...)`.

When a gate returns `True`, transport performs side effects such as:

- assigning/creating airplanes,
- reserving stands,
- assigning routes,
- sending runtime commands (`spawn_plane`, `start_path`).

Current action mapping:

- `should_schedule_departure` -> `assign_airplane_to_departure_flight` + `assign_path_to_airplane(..., destination="Departure")`.
- `should_assign_landing_plane` -> `create_and_assign_airplane_for_landing_departure`.
- `should_mark_landing_departed` -> `mark_landing_departed` (`Flight -> Ongoing`, `Airplane -> InFlight`).
- `should_reserve_landing_stand` -> `reserve_stand_and_link_airplane_for_landing_arrival` + `assign_landing_path_for_airplane`.
- `should_spawn_landing_plane` -> send landing `spawn_plane` command using setup `landing_spawn_position`.
- `should_start_departure_movement` and `should_start_landing_approach` -> send `start_path` command.

## Caveats

- `handled` and stand cache are process-local memory; restarting the process resets both.
- Landing “near” checks use 10 minutes, not 1 minute.
- Bootstrap reset is intentionally destructive and should only run at simulation startup.
