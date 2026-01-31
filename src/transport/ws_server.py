import logging, asyncio
import websockets
from datetime import datetime, timezone, timedelta
import time, math

from src.handlers.runtime_bus import RuntimeBusHandler
from src.handlers.setup_bus import SetupBusHandler
from src.transport.message_bus import WsMessageBus
from src.domain.sim_clock import SimulationClock
from src.schedulers.spawn_scheduler import SpawnScheduler
from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler
from src.utils.datetimes import as_utc
from src.path_commands import make_start_path_command
from src.services.flight_generator import RandomFlightGenerator
from src.db.engine import get_engine
from src.db import models

from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func

from src.services.spawn_tracking import ensure_airplane_row
from src.db.db_functions import (
    assign_airplane_to_departure_flight,
    assign_landing_path_for_airplane,
    assign_path_to_airplane,
    create_and_assign_airplane_for_landing_departure,
    link_airplane_to_stand,
    list_flights_in_sliding_window,
    normalize_flight_type,
    reserve_stand_and_link_airplane_for_landing_arrival,
    mark_landing_departed,
)

setup_bus: SetupBusHandler | None = None


async def incoming_dispatch_loop(bus: WsMessageBus, setup_bus: SetupBusHandler, runtime_bus: RuntimeBusHandler, *, clock, clock_lock=None):

    """Smista i messaggi in entrata verso i vari handler"""

    while True:
        payload = await bus.incoming.get()
        try:
            if isinstance(payload, dict) and await handle_clock_control(
                payload, clock=clock, bus=bus, clock_lock=clock_lock
            ):
                continue

            if not setup_bus.setup_finished:
                await setup_bus.enqueue(payload)
            else:
                await runtime_bus.enqueue(payload)
        finally:
            bus.incoming.task_done()


async def flight_scheduler_loop(*, setup_bus, clock, airport_icao: str, poll_seconds: float = 30.0, pw_prefab_store, bus) -> None:
    while not setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)

    global landing_spawn_position
    landing_spawn_position = setup_bus.state.landing_spawn_position
    logging.info("[spawn_scheduler] landing_spawn_position=%s", landing_spawn_position)

    scheduler = FlightSlidingWindowScheduler(
        airport_icao=airport_icao,
        window=timedelta(hours=1),
    )

    # Debug: generate flights only after initial spawns created at least one parked airplane,
    # so the first LIAG departure can be made compatible with spawned planes.
    Session = sessionmaker(bind=get_engine(), future=True)
    timeout_s = 10.0
    start_wait = time.monotonic()
    while True:
        with Session() as session:
            parked_count = session.execute(
                select(func.count())
                .select_from(models.Airplane)
                .where(models.Airplane.status == "Parked")
            ).scalar_one()
        if parked_count and parked_count > 0:
            break
        if (time.monotonic() - start_wait) > timeout_s:
            logging.warning("[flight_scheduler] no parked airplanes after %.1fs; generating flights anyway", timeout_s)
            break
        await asyncio.sleep(0.1)

    RandomFlightGenerator(Session).generate_flights(2, ensure_in_window=True, window=scheduler.window)
    logging.info("[flight_scheduler] generated debug flights (n=2)")

    next_tick = time.monotonic()
    last_window_log = 0.0

    while True:
        now = as_utc(clock.now())

        flights = list_flights_in_sliding_window(
            airport_icao=airport_icao,
            now_utc=now,
            window=scheduler.window,
        )

        t = time.monotonic()
        if (t - last_window_log) >= poll_seconds:
            last_window_log = t
            items = [
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
                for f in flights
            ]
            logging.info("[flight_scheduler] window now=%s flights_in_window=%d flights=%s",
                now.isoformat(),
                len(items),
                items,
            )
        for flight in flights:

            flight_id = getattr(flight, "id", None)
            if not isinstance(flight_id, str) or not flight_id:
                continue

            # DEPARTURE
            if scheduler.should_schedule_departure(flight=flight, now_utc=now):
                required_type = normalize_flight_type(getattr(flight, "tipo", None))
                assignment = assign_airplane_to_departure_flight(flight_id=flight_id, required_type=required_type)
                if assignment is None:
                    logging.info("[flight_scheduler] no compatible parked airplane flight_id=%s", flight_id)
                    continue

                airplane_id, stand_id = assignment
                assign_path_to_airplane(
                    airplane_id=airplane_id,
                    source=stand_id,
                    destination="Departure",
                )

                logging.info("[flight_scheduler] departure assigned airplane_id=%s stand_id=%s flight_id=%s", airplane_id, stand_id, flight_id)
                continue

            # LANDING
            if scheduler.should_assign_landing_plane(flight=flight, now_utc=now):
                logging.info("[flight_scheduler] landing_dep: due flight_id=%s dep=%s", flight_id, getattr(flight, "departure_time", None))

                airplane_id = create_and_assign_airplane_for_landing_departure(flight_id=flight_id, prefab_picker=pw_prefab_store.pick_plane_prefab)
                if airplane_id is None:
                    logging.info("[flight_scheduler] landing_dep: could not create/link airplane flight_id=%s", flight_id)
                    continue
                logging.info("[flight_scheduler] landing_dep: linked airplane_id=%s to flight_id=%s (Ongoing)", airplane_id, flight_id)
                continue

            if scheduler.should_mark_landing_departed(flight=flight, now_utc=now):
                mark_landing_departed(flight_id=flight_id)
                logging.info("[flight_scheduler] landing_dep: departed flight_id=%s -> Ongoing", flight_id)
                continue

            # LANDING: arrival_time window -> reserve stand + link plane to stand + set Landing
            if scheduler.should_reserve_landing_stand(flight=flight, now_utc=now):
                stand_id = reserve_stand_and_link_airplane_for_landing_arrival(flight_id=flight_id)
                if stand_id is None:
                    logging.warning("[flight_scheduler] landing_arr: no available stands flight_id=%s", flight_id)
                    continue

                airplane_id = getattr(flight, "airplane_id", None)
                if isinstance(airplane_id, str):
                    assign_landing_path_for_airplane(
                        airplane_id=airplane_id,
                        stand_id=stand_id,
                    )

                logging.info("[flight_scheduler] landing_arr: stand_id=%s reserved + plane linked flight_id=%s", stand_id, flight_id)
                continue

            # START DEPARTURE MOVEMENT
            if scheduler.should_start_departure_movement(flight=flight, now_utc=now):
                airplane_id = getattr(flight, "airplane_id", None)
                if isinstance(airplane_id, str):
                    cmd = make_start_path_command(airplane_id=airplane_id)
                    logging.info("[start_path][OUT] flight_id=%s airplane_id=%s route_id=%s segments=%d now=%s",
                        flight_id, cmd["airplane_id"], cmd["route_id"], len(cmd["segments"]), now.isoformat())
                    if cmd is not None:
                        await bus.send_command(cmd)
                        logging.info("[flight_scheduler] start_path departure airplane_id=%s flight_id=%s", airplane_id, flight_id)
                continue

            # START LANDING MOVEMENT
            if scheduler.should_start_landing_approach(flight=flight, now_utc=now):
                airplane_id = getattr(flight, "airplane_id", None)
                if isinstance(airplane_id, str):
                    cmd = make_start_path_command(airplane_id=airplane_id)
                    logging.info("[start_path][OUT] flight_id=%s airplane_id=%s route_id=%s segments=%d now=%s",
             flight_id, cmd["airplane_id"], cmd["route_id"], len(cmd["segments"]), now.isoformat())
                    if cmd is not None:
                        await bus.send_command(cmd)
                        logging.info("[flight_scheduler] start_path landing airplane_id=%s flight_id=%s", airplane_id, flight_id)
                continue            

        next_tick += poll_seconds
        await asyncio.sleep(max(0.0, next_tick - time.monotonic()))


async def handle_clock_control(payload: dict, *, clock, bus, clock_lock: asyncio.Lock | None = None) -> bool:

    cmd = payload.get("command")
    if not isinstance(cmd, str):
        return False
    cmd = cmd.strip().lower()

    if cmd == "set_time_scale":
        raw = payload.get("time_scale")
        req_id = payload.get("request_id")
        before_scale = clock.time_scale
        before_now = clock.now().astimezone(timezone.utc)

        logging.info("[clock][IN] set_time_scale requested=%r request_id=%r before_scale=%.3f before_now=%s",
            payload.get("time_scale"),
            req_id,
            before_scale,
            before_now.isoformat(),
        )

        try:
            scale = float(raw)
        except (TypeError, ValueError):
            return True
        
        if not math.isfinite(scale) or scale < 0.0:
            return True
        
        if clock_lock:
            async with clock_lock:
                clock.set_time_scale(scale)
                sync = clock.make_sync()
        else:
            clock.set_time_scale(scale)
            sync = clock.make_sync()

        after_scale = clock.time_scale
        after_now = clock.now().astimezone(timezone.utc)

        logging.info(
            "[clock][APPLIED] set_time_scale applied=%.3f request_id=%r after_scale=%.3f after_now=%s",
            scale,
            req_id,
            after_scale,
            after_now.isoformat(),
        )
        
        await bus.send_command({
            "command": "clock_sync",
            "sync_id": sync.sync_id,
            "sim_unix_ms": sync.sim_unix_ms,
            "time_scale": sync.time_scale,
        })
        return True

    if cmd == "set_sim_time":
        raw_ms = payload.get("sim_unix_ms")
        try:
            sim_unix_ms = int(raw_ms)
        except (TypeError, ValueError):
            return True
        
        new_sim = datetime.fromtimestamp(sim_unix_ms / 1000.0, tz=timezone.utc)
        if clock_lock:
            async with clock_lock:
                clock.set_sim_time(new_sim)
        else:
            clock.set_sim_time(new_sim)
        return True
    
    return False


async def clock_sync_loop(bus: WsMessageBus, clock: SimulationClock, *, hz: float = 10.0, clock_lock=None):
    period = 1.0 / hz
    logging.info("Clock sync loop started: hz=%.1f", hz)
    last_log_t = 0.0
    log_every_s = 10.0

    while True:
        if clock_lock is None:
            sync = clock.make_sync()
            sim_now = clock.now()
        else:
            async with clock_lock:
                sync = clock.make_sync()
                sim_now = clock.now()

        await bus.send_command({
            "command": "clock_sync",
            "sync_id": sync.sync_id,
            "sim_unix_ms": sync.sim_unix_ms,
            "time_scale": sync.time_scale,
        })

        t = time.monotonic()
        if (t - last_log_t) >= log_every_s:
            last_log_t = t
            logging.info(
                "[clock_sync] sim_now=%s sim_unix_ms=%d time_scale=%.2f sync_id=%d",
                sim_now.astimezone(timezone.utc).isoformat(timespec="seconds"),
                sync.sim_unix_ms,
                sync.time_scale,
                sync.sync_id,
            )

        await asyncio.sleep(period)


async def echo_handler(websocket, pw_prefab_store, pw_world_state, pw_graph) -> None:
    """Handle one WebSocket client: greet, log, and echo any text received."""
    
    if setup_bus is None:
        raise RuntimeError("setup_bus is not initialized")

    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    runtime_bus = RuntimeBusHandler(pw_prefab_store)
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
    clock_lock = asyncio.Lock()

    airport_icao = getattr(pw_graph, "airport_id", None)
    if not isinstance(airport_icao, str) or not airport_icao:
        raise RuntimeError("InitGraph airport_id missing / invalid")

    logging.info("Clock init: sim_start=%s time_scale=%.2f", clock.now().isoformat(), clock.time_scale)

    dispatch_task = asyncio.create_task(incoming_dispatch_loop(bus, setup_bus, runtime_bus, clock=clock, clock_lock=clock_lock))
    spawn_task = asyncio.create_task(schedule_initial_spawns(bus, setup_bus, pw_prefab_store))
    clock_task = asyncio.create_task(clock_sync_loop(bus, clock, hz=10.0))
    flight_task = asyncio.create_task(
        flight_scheduler_loop(
            setup_bus=setup_bus,
            clock=clock,
            airport_icao=airport_icao,
            poll_seconds=30.0,
            pw_prefab_store=pw_prefab_store,
            bus=bus,
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


async def schedule_initial_spawns(bus: WsMessageBus, setup_bus: SetupBusHandler, pw_prefab_store):
    
    """Attende fine setup, poi pianifica e invia i primi spawn verso Unity"""

    while not setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)
    
    scheduler = SpawnScheduler(prefab_store=pw_prefab_store)
    commands = scheduler.plan_initial_spawns()
    if not commands:
        logging.info("No initial spawns commands generated")
        return

    for cmd in commands:
        await bus.send_command(cmd)

    logging.info("Scheduled %d initial spawn commands", len(commands))


async def main(host, port, pw_prefab_store, pw_graph, pw_world_state) -> None:
    """Start the WebSocket server and keep it running indefinitely."""
    # Initialize the setup bus handler inside the running event loop.
    global setup_bus
    setup_bus = SetupBusHandler(prefab_store=pw_prefab_store, init_graph=pw_graph)
    await setup_bus.start()

    # websockets.serve creates a server context manager; exiting it stops the server.
    
    async def _ws_handler(websocket, path=None):
        await echo_handler(
            websocket, 
            pw_prefab_store=pw_prefab_store, 
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
