import logging, asyncio
import websockets
from datetime import datetime, timezone, timedelta
import time

from src.handlers.runtime_bus import RuntimeBusHandler
from src.handlers.setup_bus import SetupBusHandler
from src.transport.message_bus import WsMessageBus
from src.domain.sim_clock import SimulationClock
from src.schedulers.spawn_scheduler import SpawnScheduler
from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler
from src.utils.datetimes import as_utc

from src.services.spawn_tracking import ensure_airplane_row
from src.db.db_functions import (
    assign_airplane_to_departure_flight,
    link_airplane_to_stand,
    list_flights_in_sliding_window,
    normalize_flight_type,
    reserve_stand_for_arrival_flight
)

setup_bus: SetupBusHandler | None = None


async def incoming_dispatch_loop(bus: WsMessageBus, setup_bus: SetupBusHandler, runtime_bus: RuntimeBusHandler):

    """Smista i messaggi in entrata verso i vari handler"""

    while True:
        payload = await bus.incoming.get()
        try:
            # Switch tra Setup Bus e Runtime Bus

            if not setup_bus.setup_finished:
                await setup_bus.enqueue(payload)
            else:
                await runtime_bus.enqueue(payload)
        finally:
            bus.incoming.task_done()


async def flight_scheduler_loop(*, setup_bus, clock, airport_icao: str, poll_seconds: float = 30.0) -> None:
    while not setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)

    scheduler = FlightSlidingWindowScheduler(
        airport_icao=airport_icao,
        window=timedelta(hours=1),
    )

    next_tick = time.monotonic()
    last_window_log = 0.0

    while True:
        now = as_utc(clock.now())

        flights = list_flights_in_sliding_window(
            airport_icao=airport_icao,
            now_utc=now,
            window=scheduler.window,
        )

        if (next_tick - last_window_log) >= poll_seconds:
            last_window_log = next_tick
            items = []
            for f in flights:
                items.append(
                    {
                        "id": getattr(f, "id", None),
                        "origin": getattr(f, "origin", None),
                        "destination": getattr(f, "destination", None),
                        "dep": getattr(f, "departure_time", None),
                        "arr": getattr(f, "arrival_time", None),
                        "tipo": getattr(f, "tipo", None),
                        "status": getattr(f, "status", None),
                        "airplane_id": getattr(f, "airplane_id", None),
                    }
                )
                logging.info("[flight_scheduler] window now=%s flights_in_window=%d flights=%s",
                    now.isoformat(),
                    len(items),
                    items,
                    )
        for flight in flights:
            
            if not scheduler.to_schedule(flight=flight, now_utc=now):
                continue

            if getattr(flight, "origin", None) != airport_icao:
                continue

            flight_id = getattr(flight, "id", None)
            if not isinstance(flight_id, str) or not flight_id:
                continue

            # DEPARTURE
            if getattr(flight, "origin", None) == airport_icao:
                required_type = normalize_flight_type(getattr(flight, "tipo", None))
                assignment = assign_airplane_to_departure_flight(
                    flight_id=flight_id,
                    required_type=required_type,
                )
                if assignment is None:
                    logging.info("[flight_scheduler] no compatible parked airplane flight_id=%s", flight_id)
                    continue

                airplane_id, stand_id = assignment
                scheduler.mark_scheduled(flight_id)
                logging.info("[flight_scheduler] departure assigned airplane_id=%s stand_id=%s flight_id=%s", airplane_id, stand_id, flight_id)
                continue

            # LANDING
            if getattr(flight, "destination", None) == airport_icao:
                flight_type = normalize_flight_type(getattr(flight, "tipo", None))

                stand_id = reserve_stand_for_arrival_flight(flight_id=flight_id, flight_type=flight_type)
                if stand_id is not None:
                    scheduler.mark_scheduled(flight_id)
                    logging.info("[flight_scheduler] landing reserved stand_id=%s flight_id=%s", stand_id, flight_id)
                    continue

                logging.warning("[flight_scheduler] landing: no free stands for Unity flight_id=%s", flight_id)

        next_tick += poll_seconds
        await asyncio.sleep(max(0.0, next_tick - time.monotonic()))


async def clock_sync_loop(bus: WsMessageBus, clock: SimulationClock, *, hz: float = 10.0):
    period = 1.0 / hz
    logging.info("Clock sync loop started: hz=%.1f", hz)

    while True:
        sync = clock.make_sync()
        await bus.send_command({
            "command": "clock_sync",
            "sync_id": sync.sync_id,
            "sim_unix_ms": sync.sim_unix_ms,
            "time_scale": sync.time_scale,
        })

        await asyncio.sleep(period)


async def echo_handler(websocket, pw_simulator, pw_world_state, pw_graph) -> None:
    """Handle one WebSocket client: greet, log, and echo any text received."""
    
    if setup_bus is None:
        raise RuntimeError("setup_bus is not initialized")

    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    runtime_bus = RuntimeBusHandler(pw_simulator)
    await runtime_bus.start()

    bus = WsMessageBus()
    await bus.start(websocket=websocket)

    def _track_spawns(payload: dict) -> None:
        cmd = payload.get("command")
        if cmd not in ("spawn_plane", "spawn"):
            return
        stand_id = payload.get("stand_id")
        prefab = payload.get("prefab")

        ctx = payload.get("spawn_context")
        airplane_id = payload.get("airplane_id") if isinstance(payload.get("airplane_id"), str) else None
        airplane_id = ensure_airplane_row(airplane_id=airplane_id, prefab=prefab)

        if ctx == "bootstrap":
            link_airplane_to_stand(stand_id=stand_id, airplane_id=airplane_id)

        if not isinstance(stand_id, str) or not isinstance(prefab, str):
            return

        pw_world_state.record_plane_spawn(
            stand_id = stand_id,
            prefab = prefab,
            position = payload.get("position"),
        )

    bus.add_outgoing_hook(_track_spawns)

    clock = SimulationClock(sim_start=datetime.now(timezone.utc), time_scale=1.0)

    airport_icao = getattr(pw_graph, "airport_id", None)
    if not isinstance(airport_icao, str) or not airport_icao:
        raise RuntimeError("InitGraph airport_id missing / invalid")

    logging.info("Clock init: sim_start=%s time_scale=%.2f", clock.now().isoformat(), clock.time_scale)

    dispatch_task = asyncio.create_task(incoming_dispatch_loop(bus, setup_bus, runtime_bus))
    spawn_task = asyncio.create_task(schedule_initial_spawns(bus, setup_bus, pw_simulator))
    clock_task = asyncio.create_task(clock_sync_loop(bus, clock, hz=10.0))
    flight_task = asyncio.create_task(
        flight_scheduler_loop(
            setup_bus=setup_bus,
            clock=clock,
            airport_icao=airport_icao,
            poll_seconds=30.0,
        )
    )

    try:
        # Handshake verso Unity
        await bus.send_command({"type": "welcome", "message": "Connected to Python server"})
        await bus._recv_task

    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)
    finally:
        await bus.stop()

        for task in (dispatch_task, spawn_task, clock_task, flight_task):
            task.cancel()
        
        for task in (dispatch_task, spawn_task, clock_task, flight_task):
            try:
                await task
            except asyncio.CancelledError:
                pass


async def schedule_initial_spawns(bus: WsMessageBus, setup_bus: SetupBusHandler, simulator):
    
    """Attende fine setup, poi pianifica e invia i primi spawn verso Unity"""

    while not setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)
    
    scheduler = SpawnScheduler(simulator=simulator)
    commands = scheduler.plan_initial_spawns()
    if not commands:
        logging.info("No initial spawns commands generated")
        return

    for cmd in commands:
        await bus.send_command(cmd)

    logging.info("Scheduled %d initial spawn commands", len(commands))


async def main(host, port, pw_simulator, pw_graph, pw_world_state) -> None:
    """Start the WebSocket server and keep it running indefinitely."""
    # Initialize the setup bus handler inside the running event loop.
    global setup_bus
    setup_bus = SetupBusHandler(pw_simulator, pw_graph)
    await setup_bus.start()

    # websockets.serve creates a server context manager; exiting it stops the server.
    
    async def _ws_handler(websocket, path=None):
        await echo_handler(
            websocket, 
            pw_simulator=pw_simulator, 
            pw_world_state=pw_world_state, 
            pw_graph=pw_graph
        )

    async with websockets.serve(
        _ws_handler,
        host,
        port,
        max_size=4 * 1024 * 1024,  # allow larger JSON payloads
        ping_interval=20,
        ping_timeout=20,
        max_queue=32,
    ):
        logging.info("WebSocket server running on ws://%s:%s", host, port)
        # Keep the server alive forever; replaced by a future that never resolves.
        await asyncio.Future()
    
    if setup_bus is not None:
        await setup_bus.stop()
