import asyncio
import json
import logging

import websockets
from websockets import WebSocketServerProtocol

from src.simulator import Simulator

# Configure basic logging so connections and messages are visible in stdout.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

HOST = "0.0.0.0"
PORT = 8765

pw_simulator = Simulator()

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

    # Prefab payloads
    if _log_prefab_payload_if_any(payload):
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

    valid_splines = [s for s in splines if isinstance(s, dict)]
    if valid_splines:
        pw_simulator.add_splines(valid_splines)
    for spline in valid_splines:
        _log_single_spline(spline)


def _log_single_spline(spline: dict) -> None:
    if not isinstance(spline, dict):
        logging.debug("Invalid 'spline' payload (expected object)")
        return
    pw_simulator.add_spline(spline)
    name = spline.get("name", "<unnamed>")
    closed = spline.get("closed", False)
    knots = spline.get("knots")
    knot_count = _count_knots(knots)
    logging.info("Spline '%s' closed=%s knots=%d", name, closed, knot_count)
    pw_simulator.print_contents()


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


def _log_prefab_payload_if_any(payload: dict) -> bool:
    """Detect and log prefab name payloads."""
    if not isinstance(payload, dict):
        return False

    # New payload: { "prefabs": [ { "type": "...", "name": "..." }, ... ] }
    if "prefabs" in payload:
        prefabs_val = payload.get("prefabs", [])
        if not isinstance(prefabs_val, list):
            logging.info("Prefabs key present but not a list")
            return True

        by_type: dict[str, list[str]] = {}
        valid_prefabs: list[dict] = []
        for entry in prefabs_val:
            if not isinstance(entry, dict):
                continue
            p_type = str(entry.get("type", "")).strip()
            p_name = str(entry.get("name", "")).strip()
            if not p_type or not p_name:
                continue
            by_type.setdefault(p_type, []).append(p_name)
            valid_prefabs.append({"type": p_type, "name": p_name})

        if not by_type:
            logging.info("Prefabs received but none parsed")
            return True

        summary = " ".join(f"{t}={sorted(names)}" for t, names in by_type.items())
        total = sum(len(names) for names in by_type.values())
        logging.info("Prefabs received (%d): %s", total, summary)
        if valid_prefabs:
            pw_simulator.add_prefabs(valid_prefabs)
            pw_simulator.print_contents()
        return True

    # Legacy payload: { "aereo": "...", "mezzo": "..." }
    has_aereo = "aereo" in payload
    has_mezzo = "mezzo" in payload
    if has_aereo or has_mezzo:
        a_val = payload.get("aereo", "")
        m_val = payload.get("mezzo", "")
        logging.info("Prefabs received: aereo=%s mezzo=%s", a_val, m_val)
        legacy = []
        if a_val:
            legacy.append({"type": "aereo", "name": a_val})
        if m_val:
            legacy.append({"type": "mezzo", "name": m_val})
        if legacy:
            pw_simulator.add_prefabs(legacy)
        return True

    return False


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
