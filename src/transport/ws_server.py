from datetime import datetime, timezone
import asyncio, logging
import websockets

from src.handlers.runtime_bus import RuntimeBusHandler
from src.handlers.setup_bus import SetupBusHandler
from src.transport.message_bus import WsMessageBus
from src.domain.sim_clock import SimulationClock
from src.domain.status_constants import BUS_COMMANDS, WEBSOCKET_CONFIG

from src.transport.session import SessionContext
from src.transport.loops.clock import handle_clock_control, clock_sync_loop
from src.transport.loops.spawn_scheduling import schedule_initial_spawns
from src.transport.loops.flight_scheduling import flight_scheduler_loop
from src.transport.loops.flight_actions import FlightActions, build_flight_actions
from src.transport.hooks.spawn_tracking import make_spawn_tracking_hook
from src.transport.tasks import run_tasks  # if you use the helper


async def incoming_dispatch_loop(ctx: SessionContext) -> None:

    """Smista i messaggi in entrata verso i vari handler"""

    while True:

        # Get incoming payload from message bus
        payload = await ctx.bus.incoming.get()
        try:
            # If clock control command, handle directly
            if isinstance(payload, dict) and await handle_clock_control(ctx, payload):
                continue

            # If setup not finished, route to setup bus, otherwise route to runtime bus
            if not ctx.setup_bus.setup_finished:
                await ctx.setup_bus.enqueue(payload)
            else:
                await ctx.runtime_bus.enqueue(payload)
        finally:
            ctx.bus.incoming.task_done()


async def echo_handler(websocket, setup_bus, prefab_store, world_state, graph, flight_actions) -> None:
    """Handle one WebSocket client: greet, log, and echo any text received."""
    
    # Strict check on setup bus to exist
    if setup_bus is None:
        raise RuntimeError("setup_bus is not initialized")

    # Logs the connecting client's remote address
    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    # Initialize and start a Message Bus serving this websocket connection
    bus = WsMessageBus()
    await bus.start(websocket=websocket)

    # Register the hook on the bus to trigger it for every payload
    bus.add_outgoing_hook(make_spawn_tracking_hook(world_state=world_state))

    # Initialize Simulation Clock and a clock lock to guard it
    clock = SimulationClock(sim_start=datetime.now(timezone.utc), time_scale=1.0)
    clock_lock = asyncio.Lock()

    # Create Clock Changed event for wake event in schedulers
    clock_changed = asyncio.Event()

    # Create a Runtime Bus Handler instance and start it
    runtime_bus = RuntimeBusHandler(
        prefab_store,
        clock=clock,
        clock_lock=clock_lock,
        clock_changed=clock_changed,
    )
    await runtime_bus.start()

    # Extract and validate airport ICAO from the graph
    airport_icao = getattr(graph, "airport_id", None)
    if not isinstance(airport_icao, str) or not airport_icao:
        raise RuntimeError("InitGraph airport_id missing / invalid")

    logging.info("Clock init: sim_start=%s time_scale=%.2f", clock.now().isoformat(), clock.time_scale)

    ctx = SessionContext(
        bus=bus,
        setup_bus=setup_bus,
        runtime_bus=runtime_bus,
        clock=clock,
        clock_lock=clock_lock,
        clock_changed=clock_changed,
        prefab_store=prefab_store,
        graph=graph,
        world_state=world_state,
        airport_icao=airport_icao,
        flight_actions=flight_actions
    )

    # Create and start the Dispatch Loop
    dispatch_task = asyncio.create_task(incoming_dispatch_loop(ctx))

    # Start initial spawns and periodic clock sync tasks
    spawn_task = asyncio.create_task(schedule_initial_spawns(ctx))
    clock_task = asyncio.create_task(clock_sync_loop(ctx))

    # Start flight scheduler task with clock lock and wake event passed
    flight_task = asyncio.create_task(flight_scheduler_loop(ctx, poll_seconds=30.0,))

    # Always stop the bus, cancel all background tasks and await each task to finish for graceful close
    try:
        async with run_tasks(dispatch_task, spawn_task, clock_task, flight_task):
            await bus.send_command({"type": BUS_COMMANDS.WELCOME, "message": "Connected to Python server"})
            await bus._recv_task
    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)
    finally:
        await bus.stop()


async def main(host, port, app_container, *, flight_actions: FlightActions) -> None:
    """Start the WebSocket server and keep it running indefinitely."""

    # Initialize the setup bus handler inside the running event loop and start it
    setup_bus = SetupBusHandler(prefab_store=app_container.prefab_store, init_graph=app_container.graph)
    await setup_bus.start()

    flight_actions = build_flight_actions(Session=app_container.Session)
    
    # Define the handler for every connection that delegates to Echo Handler
    async def _ws_handler(websocket, path=None):
        await echo_handler(
            websocket,
            setup_bus=setup_bus,
            prefab_store=app_container.prefab_store, 
            world_state=app_container.world_state, 
            graph=app_container.graph,
            flight_actions=flight_actions,
        )

    # Start websocket server with config, limits, timeouts and queue settings
    async with websockets.serve(
        _ws_handler,
        host,
        port,
        max_size=WEBSOCKET_CONFIG.MAX_SIZE,  # allow larger JSON payloads
        ping_interval=WEBSOCKET_CONFIG.PING_INTERVAL,
        ping_timeout=WEBSOCKET_CONFIG.PING_TIMEOUT,
        max_queue=WEBSOCKET_CONFIG.MAX_QUEUE,
    ):
        logging.info("WebSocket server running on ws://%s:%s", WEBSOCKET_CONFIG.HOST, WEBSOCKET_CONFIG.PORT)

        # Keep the server alive forever; replaced by a future that never resolves.
        await asyncio.Future()
    
    if setup_bus is not None:
        await setup_bus.stop()
