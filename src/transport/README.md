# `src/transport` Workflow Guide

This document describes the transport layer in `src/transport`, aligned with the project architecture in `../../README.md`.

## Scope

`src/transport` is the runtime bridge between Unity and backend domain logic.  
It provides:

- WebSocket server lifecycle
- Incoming/outgoing message queues
- Dispatch to setup/runtime handlers
- Clock control and periodic clock sync
- Coordination of spawn and flight scheduler loops

## Files and Responsibilities

### `message_bus.py`

Defines `WsMessageBus`, an async queue-based adapter around a WebSocket connection.

- `incoming`: decoded JSON payloads received from Unity.
- `outgoing`: commands/events to send to Unity.
- `start()`: launches `_recv_loop` + `_send_loop`.
- `send_command(payload)`: runs outgoing hooks, then enqueues payload.
- `add_outgoing_hook(hook)`: register pre-send hooks (used for spawn tracking).
- `stop()`: closes loops via `closed` flag + `None` sentinel.

Core behavior:

- `_recv_loop` parses JSON and pushes valid payloads to `incoming`.
- `_send_loop` consumes `outgoing`, serializes to JSON, and sends over WebSocket.
- On connection close, bus marks itself closed and drains gracefully.

### `ws_server.py`

Main transport orchestrator. It wires together:

- `SetupBusHandler` and `RuntimeBusHandler`
- `WsMessageBus`
- `SimulationClock`
- Initial spawn scheduler
- Flight sliding-window scheduler

Main public entrypoint:

- `main(host, port, *, container=AppContainer(...))`

This initializes setup handler and runs `websockets.serve(...)` indefinitely.

## End-to-End Transport Workflow

### 1) Server bootstrap

1. `main(...)` creates global `setup_bus = SetupBusHandler(...)`.
2. Starts setup handler worker task.
3. Starts WebSocket server (`ws://<host>:<port>`).
4. Each client connection is handled by `echo_handler(...)`.

### 2) Per-connection session startup (`echo_handler`)

For each Unity client:

1. Creates and starts `WsMessageBus`.
2. Registers outgoing hook `_track_spawns`:
   - on `spawn_plane` commands, ensures `Airplane` DB row exists
   - links stand->airplane for bootstrap spawns
   - records in-memory world state snapshot
3. Initializes `SimulationClock` and synchronization primitives:
   - `clock_lock`
   - `clock_changed` event
4. Starts `RuntimeBusHandler`.
5. Starts long-running tasks:
   - `incoming_dispatch_loop(...)`
   - `schedule_initial_spawns(...)`
   - `clock_sync_loop(...)`
   - `flight_scheduler_loop(...)`
6. Sends welcome payload to Unity and waits until receive loop ends.

### 3) Incoming message dispatch

`incoming_dispatch_loop(...)` consumes `bus.incoming` and routes payloads:

1. First, checks `handle_clock_control(...)` for clock commands:
   - `set_time_scale`
   - `set_sim_time`
2. If setup is not finished: forward to `setup_bus`.
3. After setup completion: forward to `runtime_bus`.

This guarantees setup messages and runtime messages are handled by different subsystems in the correct phase.

### 4) Clock control and sync

Two complementary flows run in transport:

- **Clock control (incoming):**
  - `handle_clock_control(...)` applies time scale / sim time updates.
  - Emits immediate `clock_sync` after `set_time_scale`.
  - Sets `clock_changed` to wake scheduler loops quickly.

- **Clock sync stream (outgoing):**
  - `clock_sync_loop(...)` sends `clock_sync` at fixed frequency (`hz=10`).
  - Writes periodic clock events to JSONL log (`append_event`) for dashboard websocket consumers.

### 5) Initial spawn scheduling

`schedule_initial_spawns(...)`:

1. Waits for setup completion.
2. Emits `simulation_start` event to logs.
3. Uses `SpawnScheduler.plan_initial_spawns()` to produce spawn commands.
4. Sends generated spawn commands through `bus.send_command(...)`.

### 6) Flight scheduling loop

`flight_scheduler_loop(...)` runs continuously after setup.

Responsibilities:

- Waits for setup-complete and obtains landing spawn position.
- Ensures parked airplanes are available (with timeout) before generating random flights.
- Polls flights in sliding window using simulation clock time.
- Executes stage-driven flight actions:
  - departure assignment + path assignment
  - inbound airplane creation for arrivals
  - departure/arrival status transitions
  - stand reservation and landing path assignment
  - `start_path` and `spawn_plane` command emission
- Uses adaptive real sleep based on simulation `time_scale`.
- Uses `clock_changed` event for immediate wake-ups on time changes.

## Message Lifecycle

### Unity -> backend path

`WebSocket frame` -> `WsMessageBus._recv_loop` -> `bus.incoming` -> `incoming_dispatch_loop` ->  
`setup_bus` or `runtime_bus` (or clock command path).

### Backend -> Unity path

`scheduler/handler command` -> `bus.send_command` -> outgoing hooks -> `bus.outgoing` -> `WsMessageBus._send_loop` -> `WebSocket frame`.

## Concurrency Model

Transport runs multiple async tasks per connection:

- Bus receive loop
- Bus send loop
- Incoming dispatcher
- Clock sync loop
- Initial spawn scheduling task
- Flight scheduler loop
- Runtime bus loop (started by runtime handler)

Shared clock state uses:

- `clock_lock` for atomic clock updates/reads when needed
- `clock_changed` event for cross-task wake signaling

## Error Handling and Shutdown

Per-connection shutdown (`echo_handler` finally block):

1. Stops message bus.
2. Cancels spawned tasks (`dispatch`, `spawn`, `clock`, `flight`).
3. Awaits cancellation completion to avoid dangling tasks.

At server scope:

- WebSocket context manager handles listener lifecycle.
- `setup_bus.stop()` is called when server context exits.

## Integration Notes

Transport depends on these non-transport layers:

- `src/handlers/*` for setup/runtime domain event processing
- `src/schedulers/*` for spawn and flight orchestration
- `src/db/db_functions.py` for state transitions
- `src/services/spawn_tracking.py` for DB row guarantees on spawns
- `src/domain/sim_clock.py` for authoritative simulation time
- `src/utils/event_log.py` for dashboard-consumable event stream

The transport layer itself does not define business entities; it coordinates message flow and timing across subsystems.

## Run Context

Transport is started indirectly by root server entrypoint:

```bash
python -m src.server
```

This calls `src.transport.ws_server.main(...)` with initialized shared state objects.
