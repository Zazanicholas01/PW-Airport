from datetime import datetime, timezone
import asyncio, logging
import websockets
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from src.handlers.runtime_bus import RuntimeBusHandler
from src.handlers.setup_bus import SetupBusHandler
from src.transport.message_bus import WsMessageBus
from src.domain.sim_clock import SimulationClock
from src.services.ground_vehicle_coordinator import GroundVehicleCoordinator
from src.domain.status_constants import BUS_COMMANDS, DASHBOARD_COMMANDS, WEBSOCKET_CONFIG

from src.transport.session import SessionContext
from src.transport.loops.clock import handle_clock_control, clock_sync_loop
from src.transport.loops.spawn_scheduling import schedule_initial_spawns
from src.transport.loops.flight_scheduling import flight_scheduler_loop
from src.transport.loops.flight_actions import FlightActions
from src.transport.loops.build_flight_actions import build_flight_actions
from src.transport.hooks.spawn_tracking import make_spawn_tracking_hook
from src.transport.command_builders import build_welcome
from src.db import db_functions
from src.utils.event_log import append_event


# Stable sender used by global loops
class ActiveUnityBus:
    def __init__(self) -> None:
        self._bus = None
        self._lock = asyncio.Lock()
    
    async def set_bus(self, bus) -> None:
        async with self._lock:
            self._bus = bus
    
    async def clear_bus(self, bus) -> bool:
        async with self._lock:
            if self._bus is bus:
                self._bus = None
                return True
            return False
    
    async def send_command(self, payload: dict) -> None:
        async with self._lock:
            bus = self._bus
        
        if bus is None:
            return
        
        await bus.send_command(payload)

# Dataclass that holds the long-lived runtime objects
@dataclass
class ServerRuntime:
    bus: ActiveUnityBus
    setup_bus: Any
    runtime_bus: Any
    clock: Any
    clock_lock: asyncio.Lock
    clock_changed: asyncio.Event
    spawn_task: asyncio.Task | None = None
    clock_task: asyncio.Task | None = None
    flight_task: asyncio.Task | None = None
    unity_attached: bool = False
    auto_paused_on_disconnect: bool = False
    resume_time_scale: float = 1.0


async def pause_simulation_for_disconnect(server_runtime: ServerRuntime) -> None:
    async with server_runtime.clock_lock:

        # Retrieve current time scale
        current_scale = float(server_runtime.clock.time_scale)

        if not server_runtime.auto_paused_on_disconnect:
            server_runtime.resume_time_scale = current_scale
        
        # Freeze simulation by setting time scale to 0
        server_runtime.clock.set_time_scale(0.0)
    
    # Set flags about disconnection
    server_runtime.auto_paused_on_disconnect = True
    server_runtime.unity_attached = False
    server_runtime.clock_changed.set()

    logging.warning(
        "[runtime] Unity client lost -> simulation paused (resume_scale=%.3f)",
        server_runtime.resume_time_scale,
    )


async def resume_simulation_after_reconnect(server_runtime: ServerRuntime) -> None:
    async with server_runtime.clock_lock:

        # If freezed, resume simulation else continue freezing
        if server_runtime.auto_paused_on_disconnect:
            resume_scale = float(server_runtime.resume_time_scale)
            server_runtime.clock.set_time_scale(resume_scale)
        else:
            resume_scale = float(server_runtime.clock.time_scale)
    
    # Reset flags about disconnection
    server_runtime.auto_paused_on_disconnect = False
    server_runtime.unity_attached = True
    server_runtime.clock_changed.set()

    logging.info(
        "[runtime] Unity client attached -> simulation resumed (time_scale=%.3f)",
        resume_scale,
    )


async def incoming_dispatch_loop(ctx: SessionContext, incoming_queue: asyncio.Queue) -> None:

    """Smista i messaggi in entrata verso i vari handler"""

    while True:

        # Get incoming payload from message bus
        payload = await incoming_queue.get()
        try:
            # If clock control command, handle directly
            if isinstance(payload, dict) and await handle_clock_control(ctx, payload):
                continue

            if isinstance(payload, dict) and payload.get("command") == DASHBOARD_COMMANDS.HIGHLIGHT_FLIGHT:
                flight_id = payload.get("flight_id")
                if isinstance(flight_id, str) and flight_id.strip():
                    redirect_url = f"/flight/{quote(flight_id, safe='')}"
                    append_event({
                        "type": "dashboard_redirect",
                        "command": DASHBOARD_COMMANDS.HIGHLIGHT_FLIGHT,
                        "flight_id": flight_id,
                        "redirect_url": redirect_url,
                    })
                    logging.info(
                        "[highlight_flight] received from Unity flight_id=%s airplane_id=%s redirect_url=%s",
                        flight_id,
                        payload.get("airplane_id"),
                        redirect_url,
                    )
                else:
                    logging.warning("[highlight_flight] ignored missing flight_id payload=%r", payload)
                continue

            # If setup not finished, route to setup bus, otherwise route to runtime bus
            if not ctx.setup_bus.setup_completed:
                await ctx.setup_bus.enqueue(payload)
            else:
                await ctx.runtime_bus.enqueue(payload)
        finally:
            incoming_queue.task_done()


async def echo_handler(
        websocket, 
        server_runtime: ServerRuntime,
        *, 
        prefab_store, 
        world_state, 
        graph, 
        Session, 
        flight_actions: FlightActions, 
        commands
    ) -> None:
    """Attach one Unity WebSocket client to the long-lived backend runtime"""

    # Logs the connecting client's remote address
    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    # Initialize and start a Message Bus serving this websocket connection
    ws_bus = WsMessageBus()
    await ws_bus.start(websocket=websocket)

    # Register the hook on the ws_bus to trigger it for every payload
    ws_bus.add_outgoing_hook(make_spawn_tracking_hook(world_state=world_state, Session=Session))

    # Set bus on server runtime and wait for reconnection
    await server_runtime.bus.set_bus(ws_bus)
    await resume_simulation_after_reconnect(server_runtime=server_runtime)

    # Extract and validate airport ICAO from the graph
    airport_icao = getattr(graph, "airport_id", None)
    if not isinstance(airport_icao, str) or not airport_icao:
        raise RuntimeError("InitGraph airport_id missing / invalid")

    ctx = SessionContext(
        bus=server_runtime.bus,
        setup_bus=server_runtime.setup_bus,
        runtime_bus=server_runtime.runtime_bus,
        ground_ops=None,
        clock=server_runtime.clock,
        clock_lock=server_runtime.clock_lock,
        clock_changed=server_runtime.clock_changed,
        prefab_store=prefab_store,
        graph=graph,
        world_state=world_state,
        Session=Session,
        airport_icao=airport_icao,
        flight_actions=flight_actions,
        commands=commands
    )

    # Create and start the Dispatch Loop
    dispatch_task = asyncio.create_task(incoming_dispatch_loop(ctx, ws_bus.incoming))

    # Each phone connection attaches to the existing runtime
    # Disconnection no longer destroys scheduler / clock / global runtime
    def _log_task_result(task: asyncio.Task, name: str) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            logging.info("[%s] Task cancelled", name)
            return
        except Exception:
            logging.exception("[%s] Task inspection failed", name)
            return

        if exc is not None:
            logging.error("[%s] Task failed: %r", name, exc, exc_info=exc)
        else:
            logging.warning("[%s] Task ended normally", name)

    dispatch_task.add_done_callback(lambda t: _log_task_result(t, "dispatch"))

    try:
        await server_runtime.bus.send_command(
            commands.welcome(message="Connected to Python server")
        )
        await ws_bus._recv_task
    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)
        
    finally:
        dispatch_task.cancel()
        try:
            await dispatch_task
        except asyncio.CancelledError:
            pass

        was_active = await server_runtime.bus.clear_bus(ws_bus)
        if was_active:
            await pause_simulation_for_disconnect(server_runtime=server_runtime)

        await ws_bus.stop()



async def main(host, port, *, container=None) -> None:
    """Start the WebSocket server and keep it running indefinitely."""

    if container is None:
        raise TypeError("main() missing required keyword argument: 'container'")

    db_functions.configure_session_factory(container.Session)

    # Initialize the setup bus handler inside the running event loop and start it
    setup_bus = SetupBusHandler(
        prefab_store=container.prefab_store,
        init_graph=container.graph,
        session_factory=container.Session,
    )
    await setup_bus.start()

    flight_actions = build_flight_actions(Session=container.Session)

    # Create clock related global runtime objects
    clock = SimulationClock(sim_start=datetime.now(timezone.utc), time_scale=1.0)
    clock_lock = asyncio.Lock()
    clock_changed = asyncio.Event()
    initial_spawns_ready = asyncio.Event()

    # Create Active Unity Bus obejct
    active_unity_bus = ActiveUnityBus()

    # Create Ground Vehicle Coordinator
    ground_ops = GroundVehicleCoordinator(
        container.Session,
        bus=active_unity_bus,
        commands=container.commands,
        clock=clock,
        clock_lock=clock_lock,
        clock_changed=clock_changed,
    )

    # Create and start Runtime bus handler
    runtime_bus = RuntimeBusHandler(
        container.prefab_store,
        session_factory=container.Session,
        bus=active_unity_bus,
        commands=container.commands,
        clock=clock,
        clock_lock=clock_lock,
        clock_changed=clock_changed,
        ground_ops=ground_ops,
    )
    await runtime_bus.start()

    # Create Personal Airport ICAO
    airport_icao = getattr(container.graph, "airport_id", None)
    if not isinstance(airport_icao, str) or not airport_icao:
        raise RuntimeError("InitGraph airport_id missing or invalid")
    
    logging.info("Clock init: sim_start=%s time_scale=%.2f", clock.now().isoformat(), clock.time_scale)

    # Global session context definition
    global_ctx = SessionContext(
        bus=active_unity_bus,
        setup_bus=setup_bus,
        runtime_bus=runtime_bus,
        ground_ops=ground_ops,
        clock=clock,
        clock_lock=clock_lock,
        clock_changed=clock_changed,
        initial_spawns_ready=initial_spawns_ready,
        prefab_store=container.prefab_store,
        graph=container.graph,
        world_state=container.world_state,
        Session=container.Session,
        airport_icao=airport_icao,
        flight_actions=flight_actions,
        commands=container.commands,
    )

    # Global Server Runtime object definition
    server_runtime = ServerRuntime(
        bus=active_unity_bus,
        setup_bus=setup_bus,
        runtime_bus=runtime_bus,
        clock=clock,
        clock_lock=clock_lock,
        clock_changed=clock_changed,
    )

    # Create global async tasks
    server_runtime.spawn_task = asyncio.create_task(schedule_initial_spawns(global_ctx))
    server_runtime.clock_task = asyncio.create_task(clock_sync_loop(global_ctx))
    server_runtime.flight_task = asyncio.create_task(
        flight_scheduler_loop(global_ctx, poll_seconds=30.0)
    )

    # Task logging function
    def _log_task_result(task: asyncio.Task, name: str) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            logging.info("[%s] Task cancelled", name)
            return
        except Exception:
            logging.exception("[%s] Task inspection failed", name)
            return

        if exc is not None:
            logging.error("[%s] Task failed: %r", name, exc, exc_info=exc)
        else:
            logging.warning("[%s] Task ended normally", name)

    for name, task in (
        ("spawn", server_runtime.spawn_task),
        ("clock_sync", server_runtime.clock_task),
        ("flight_scheduler", server_runtime.flight_task),
    ):
        task.add_done_callback(lambda t, n=name: _log_task_result(t, n))
    
    # Define the handler for every connection that delegates to Echo Handler
    async def _ws_handler(websocket, path=None):
        await echo_handler(
            websocket,
            server_runtime=server_runtime,
            prefab_store=container.prefab_store,
            world_state=container.world_state,
            graph=container.graph,
            Session=container.Session,
            flight_actions=flight_actions,
            commands=container.commands
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
    
    # Cleanup for global tasks
    for task in (server_runtime.spawn_task, server_runtime.clock_task, server_runtime.flight_task):
        if task is not None:
            task.cancel()
        
    for task in (server_runtime.spawn_task, server_runtime.clock_task, server_runtime.flight_task):
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    if setup_bus is not None:
        await setup_bus.stop()
