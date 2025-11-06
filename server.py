from __future__ import annotations

import asyncio
import csv
import json
import math
import random
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import websockets

HOST = "0.0.0.0"
PORT = 8765

# === Multi-cube ===
TARGETS = ["CUBE_1", "CUBE_2", "CUBE_3"]

# === Waypoints builder as provided ===
def build_waypoints() -> list[dict[str, float]]:
    waypoints: list[dict[str, float]] = []

    def add_point(point: tuple[float, float, float]) -> None:
        if waypoints:
            last = waypoints[-1]
            if all(abs(last[axis] - coord) < 1e-6 for axis, coord in zip(("x", "y", "z"), point)):
                return
        waypoints.append({"x": point[0], "y": point[1], "z": point[2]})

    def sample_line(start: tuple[float, float, float], end: tuple[float, float, float], segments: int) -> None:
        for step in range(segments + 1):
            t = step / segments
            add_point((start[0] + (end[0] - start[0]) * t,
                       start[1] + (end[1] - start[1]) * t,
                       start[2] + (end[2] - start[2]) * t))

    def sample_arc(center: tuple[float, float, float], radius: float, start_deg: float, end_deg: float, segments: int) -> None:
        start_rad = math.radians(start_deg)
        end_rad = math.radians(end_deg)
        for step in range(segments + 1):
            t = step / segments
            angle = start_rad + (end_rad - start_rad) * t
            x = center[0] + radius * math.cos(angle)
            z = center[2] + radius * math.sin(angle)
            add_point((x, center[1], z))

    sample_line((0.0, 0.0, 0.0), (7.0, 0.0, 0.0), segments=5)
    sample_arc(center=(7.0, 0.0, 2.5), radius=2.5, start_deg=-90, end_deg=45, segments=10)
    last_point = tuple(waypoints[-1][axis] for axis in ("x", "y", "z"))
    sample_line(last_point, (15.0, 3.0, 20.0), segments=10)
    sample_arc(center=(10.0, 3.0, 24.0), radius=5.0, start_deg=-60, end_deg=120, segments=16)
    last_point = tuple(waypoints[-1][axis] for axis in ("x", "y", "z"))
    sample_line(last_point, (0.0, 2.5, 28.0), segments=8)
    return waypoints

WAYPOINTS = build_waypoints()
SPEED_MPS = 2.0
POLL_HZ = 5

POS_CSV = Path(__file__).with_name("pos.csv")
ROUTE_LOG_CSV = Path(__file__).with_name("route_log.csv")


def append_position_to_csv(target_id: str, t_sim: Optional[float], pos: Dict[str, float]) -> None:
    """Append a sample to pos.csv, including target_id."""
    exists = POS_CSV.exists()
    with POS_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "t_sim", "x", "y", "z"])
        w.writerow([
            target_id,
            "" if t_sim is None else f"{t_sim:.3f}",
            f"{pos['x']:.6f}",
            f"{pos['y']:.6f}",
            f"{pos['z']:.6f}",
        ])

def log_route_event(target_id: str, event: str, ref_msg_id: str | None, t_sim: Optional[float]) -> None:
    """Log 'start' and 'stop' events to route_log.csv with a host timestamp too."""
    exists = ROUTE_LOG_CSV.exists()
    with ROUTE_LOG_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "event", "t_host", "t_sim", "ref_msg_id"])
        w.writerow([target_id, event, f"{time.time():.3f}", "" if t_sim is None else f"{t_sim:.3f}", ref_msg_id or ""])

async def send_and_wait_ack(ws, cmd_payload: dict) -> None:
    await ws.send(json.dumps(cmd_payload))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("type") == "event":
            if msg.get("event") == "command.ack" and msg.get("ref_msg_id") == cmd_payload["msg_id"]:
                # ACK received
                return
            if msg.get("event") == "command.error" and msg.get("ref_msg_id") == cmd_payload["msg_id"]:
                raise RuntimeError("Command failed: " + (msg.get("detail") or ""))

async def query_position(ws, target_id: str) -> Tuple[Dict[str, float], Optional[float], bool]:
    """Send get.position for target; return (pos, t_sim, route_completed_flag)."""
    mid = str(uuid.uuid4())
    await ws.send(json.dumps({"type": "query", "query": "get.position", "target_id": target_id, "msg_id": mid}))
    route_completed = False
    while True:
        msg = json.loads(await ws.recv())
        # Catch async events in-band
        if msg.get("type") == "event":
            if msg.get("event") == "route.complete" and msg.get("target_id") == target_id:
                route_completed = True
            # continue waiting for our response
            continue
        if msg.get("type") == "response" and msg.get("msg_id") == mid:
            return msg["result"], msg.get("t_sim"), route_completed

async def run_route_once(ws, target_id: str) -> None:
    """Send a route to one target, log start/stop, and sample positions until it completes."""
    cmd_id = str(uuid.uuid4())
    cmd = {
        "type": "command",
        "command": "set.route",
        "target_id": target_id,
        "msg_id": cmd_id,
        "args": {"waypoints": WAYPOINTS, "speed": SPEED_MPS},
    }

    # START
    await send_and_wait_ack(ws, cmd)
    log_route_event(target_id, "start", cmd_id, t_sim=None)

    # Poll positions until route.complete arrives (observed via query loop)
    try:
        while True:
            pos, t_sim, done = await query_position(ws, target_id)
            append_position_to_csv(target_id, t_sim, pos)
            print(f"[{target_id}] t={t_sim:7.2f}  x={pos['x']:6.2f}  y={pos['y']:5.2f}  z={pos['z']:6.2f}")
            if done:
                # STOP
                log_route_event(target_id, "stop", cmd_id, t_sim)
                print(f"[{target_id}] Route complete.")
                break
            await asyncio.sleep(1.0 / POLL_HZ)
    except websockets.ConnectionClosed:
        print("[WS] Disconnected")
        return

async def handler(ws):
    print("[WS] Unity connected")

    # Cycle forever: random target each time; avoid immediate repeats
    last = None
    while True:
        candidates = [t for t in TARGETS if t != last] or TARGETS
        target = random.choice(candidates)
        last = target
        print(f"[WS] Selected target: {target}")
        await run_route_once(ws, target)

async def main():
    async with websockets.serve(handler, HOST, PORT):
        print(f"[WS] Listening on ws://{HOST}:{PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
0
