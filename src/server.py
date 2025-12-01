import asyncio
import json
import logging

import websockets
from websockets import WebSocketServerProtocol

# Configure basic logging so connections and messages are visible in stdout.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

HOST = "0.0.0.0"
PORT = 8765


def _log_spline_payload_if_any(message: str) -> None:
    """Try to parse and log spline payloads sent from Unity."""
    try:
        payload = json.loads(message)
    except (json.JSONDecodeError, TypeError) as exc:
        logging.debug("Non-JSON message ignored (len=%d): %s", len(message), exc)
        return

    if not isinstance(payload, dict):
        logging.debug("Received JSON that is not an object")
        return

    # New path: single-spline messages { "spline": { ... } }
    if "spline" in payload:
        spline = payload["spline"]
        _log_single_spline(spline)
        return

    # Legacy path: array of splines { "splines": [ ... ] }
    if "splines" not in payload:
        logging.debug("Received JSON without 'spline'/'splines' key")
        return

    splines = payload.get("splines", [])
    if not isinstance(splines, list):
        logging.debug("Invalid spline payload: 'splines' is not a list")
        return

    for spline in splines:
        _log_single_spline(spline)


def _log_single_spline(spline: dict) -> None:
    if not isinstance(spline, dict):
        logging.debug("Invalid 'spline' payload (expected object)")
        return
    name = spline.get("name", "<unnamed>")
    closed = spline.get("closed", False)
    knots = spline.get("knots")
    knot_count = _count_knots(knots)
    logging.info("Spline '%s' closed=%s knots=%d", name, closed, knot_count)


def _count_knots(knots) -> int:
    """Count knot entries regardless of dict or list representation."""
    if knots is None:
        return 0
    if isinstance(knots, dict):
        return len(knots)
    if isinstance(knots, list):
        return len(knots)
    logging.debug("Knots payload is neither dict nor list: %s", type(knots).__name__)
    return 0


async def echo_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle one WebSocket client: greet, log, and echo any text received."""
    peer = websocket.remote_address
    logging.info("Client connected: %s", peer)

    try:
        # Send an initial handshake payload so the client knows it is connected.
        await websocket.send(json.dumps({"type": "welcome", "message": "Connected to Python WebSocket server"}))
        # Iterate over every incoming message and send it back unchanged in a JSON envelope.
        async for message in websocket:
            _log_spline_payload_if_any(message)
            await websocket.send(json.dumps({"type": "echo", "message": message}))
    except websockets.ConnectionClosed:
        logging.info("Client %s disconnected", peer)


async def main() -> None:
    """Start the WebSocket server and keep it running indefinitely."""
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down server")
