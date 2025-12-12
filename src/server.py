import asyncio
import json
import logging

import websockets
from websockets import WebSocketServerProtocol

from src.simulator import Simulator
from src.init_graph import InitGraph
from src.setup_bus import SetupBusHandler
from src.message_bus import WsMessageBus
from src.spawn_scheduler import SpawnScheduler
from src.runtime_bus import RuntimeBusHandler

######## LOGGING CONFIGURATION ########

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

######## BASIC WEBSOCKET SERVER CONFIGURATION ########

HOST = "0.0.0.0"
PORT = 8765

######## GLOBAL OBJECT INSTANCES ########

pw_simulator = Simulator()
pw_graph = InitGraph("LIAG")

setup_bus: SetupBusHandler | None = None
runtime_bus: RuntimeBusHandler | None = None


######## FUNZIONI ASINCRONE PER CREAZIONE TASK ASYNCIO


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


######## WEBSOCKET ECHO HANDLER ########


async def echo_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle one WebSocket client: greet, log, and echo any text received."""
    
    if setup_bus is None:
        raise RuntimeError("setup_bus is not initialized")

    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    runtime_bus = RuntimeBusHandler(pw_simulator)
    await runtime_bus.start()

    bus = WsMessageBus()
    await bus.start(websocket=websocket)

    dispatch_task = asyncio.create_task(incoming_dispatch_loop(bus, setup_bus, runtime_bus))
    spawn_task = asyncio.create_task(schedule_initial_spawns(bus, setup_bus, pw_simulator))

    try:
        # Handshake verso Unity
        await bus.send_command({"type": "welcome", "message": "Connected to Python server"})

        await asyncio.gather(bus._recv_task, bus._send_task, dispatch_task, spawn_task)

    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)
    finally:
        await bus.stop()
        dispatch_task.cancel()
        spawn_task.cancel()

        for task in (dispatch_task, spawn_task):
            try:
                await task
            except asyncio.CancelledError:
                pass


######## MAIN SERVER STARTUP ########


async def main() -> None:
    """Start the WebSocket server and keep it running indefinitely."""
    # Initialize the setup bus handler inside the running event loop.
    global setup_bus
    setup_bus = SetupBusHandler(pw_simulator, pw_graph)
    await setup_bus.start()

    # websockets.serve creates a server context manager; exiting it stops the server.
    
    async with websockets.serve(
        echo_handler,
        HOST,
        PORT,
        max_size=4 * 1024 * 1024,  # allow larger JSON payloads
        ping_interval=20,
        ping_timeout=20,
        max_queue=32,
    ):
        logging.info("WebSocket server running on ws://%s:%s", HOST, PORT)
        # Keep the server alive forever; replaced by a future that never resolves.
        await asyncio.Future()
    
    if setup_bus is not None:
        await setup_bus.stop()


##### ENTRY POINT ########


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down server")
