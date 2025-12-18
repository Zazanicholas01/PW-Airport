import logging, asyncio
import websockets
from datetime import datetime, timezone

from src.handlers.runtime_bus import RuntimeBusHandler
from src.handlers.setup_bus import SetupBusHandler
from src.transport.message_bus import WsMessageBus
from src.domain.sim_clock import SimulationClock
from src.schedulers.spawn_scheduler import SpawnScheduler

from src.services.spawn_tracking import ensure_airplane_row
from src.db.db_functions import link_airplane_to_stand


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

async def echo_handler(websocket, pw_simulator, pw_world_state) -> None:
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

    logging.info("Clock init: sim_start=%s time_scale=%.2f", clock.now().isoformat(), clock.time_scale)

    dispatch_task = asyncio.create_task(incoming_dispatch_loop(bus, setup_bus, runtime_bus))
    spawn_task = asyncio.create_task(schedule_initial_spawns(bus, setup_bus, pw_simulator))
    clock_task = asyncio.create_task(clock_sync_loop(bus, clock, hz=10.0))

    try:
        # Handshake verso Unity
        await bus.send_command({"type": "welcome", "message": "Connected to Python server"})
        await bus._recv_task

    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)
    finally:
        await bus.stop()

        for task in (dispatch_task, spawn_task, clock_task):
            task.cancel()
        
        for task in (dispatch_task, spawn_task, clock_task):
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
    
    async with websockets.serve(
        echo_handler(
            pw_simulator=pw_simulator, 
            pw_world_state=pw_world_state
        ),
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