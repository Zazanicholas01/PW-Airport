import asyncio
import json
import logging

import websockets
from websockets import WebSocketServerProtocol

from src.simulator import Simulator
from src.init_graph import InitGraph
from src.setup_bus import SetupBusHandler

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

######## WEBSOCKET ECHO HANDLER ########

async def echo_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle one WebSocket client: greet, log, and echo any text received."""
    if setup_bus is None:
        raise RuntimeError("setup_bus is not initialized")

    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    try:
        # Send an initial handshake payload so the client knows it is connected.
        await websocket.send(json.dumps({"type": "welcome", "message": "Connected to Python WebSocket server"}))
        # Iterate over every incoming message and send it back unchanged in a JSON envelope.
        async for message in websocket:
            try:
                payload = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                logging.debug("Non-JSON Message Ignored")
                continue

            await setup_bus.enqueue(payload)
            await websocket.send(json.dumps({"type": "ack", "message": message}))

    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)

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
