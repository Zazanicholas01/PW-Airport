from __future__ import annotations

import asyncio
import csv
import json
import uuid
from pathlib import Path
from typing import Dict, Optional

import websockets
import math

HOST = "0.0.0.0"
PORT = 8765
TARGET_ID = "CUBE_1"

def build_waypoints() -> list[dict[str, float]]:
    """Create a compound route with straights, curves, and a gentle climb."""

    waypoints: list[dict[str, float]] = []

    def add_point(point: tuple[float, float, float]) -> None:
        if waypoints:
            last = waypoints[-1]
            if all(abs(last[axis] - coord) < 1e-6 for axis, coord in zip(("x", "y", "z"), point)):
                return
        waypoints.append({"x": point[0], "y": point[1], "z": point[2]})

    def sample_line(
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        segments: int,
    ) -> None:
        for step in range(segments + 1):
            t = step / segments
            add_point(
                (
                    start[0] + (end[0] - start[0]) * t,
                    start[1] + (end[1] - start[1]) * t,
                    start[2] + (end[2] - start[2]) * t,
                )
            )

    def sample_arc(
        center: tuple[float, float, float],
        radius: float,
        start_deg: float,
        end_deg: float,
        segments: int,
    ) -> None:
        start_rad = math.radians(start_deg)
        end_rad = math.radians(end_deg)
        for step in range(segments + 1):
            t = step / segments
            angle = start_rad + (end_rad - start_rad) * t
            x = center[0] + radius * math.cos(angle)
            z = center[2] + radius * math.sin(angle)
            add_point((x, center[1], z))

    # Taxi straight out of the stand
    sample_line((0.0, 0.0, 0.0), (15.0, 0.0, 0.0), segments=8)
    # Smooth right-hand bend that lines us up with the runway
    sample_arc(center=(15.0, 0.0, 5.0), radius=5.0, start_deg=-90, end_deg=15, segments=14)
    last_point = tuple(waypoints[-1][axis] for axis in ("x", "y", "z"))
    # Gentle climb while tracking along the runway heading
    sample_line(last_point, (40.0, 5.0, 60.0), segments=16)
    # Wide left-hand turn to begin downwind leg
    sample_arc(center=(30.0, 5.0, 80.0), radius=20.0, start_deg=-75, end_deg=105, segments=24)
    last_point = tuple(waypoints[-1][axis] for axis in ("x", "y", "z"))
    # Level off and continue outbound
    sample_line(last_point, (-10.0, 6.0, 120.0), segments=12)

    return waypoints


WAYPOINTS = build_waypoints()
SPEED_MPS = 2.0            # ~4 knots for the demo
POLL_HZ = 5                # position polling rate while moving
CSV_PATH = Path(__file__).with_name("pos.csv")


def append_position_to_csv(t_sim: Optional[float], pos: Dict[str, float]) -> None:
    """Append a sample to pos.csv, creating the file with a header if needed."""
    file_exists = CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["t_sim", "x", "y", "z"])
        writer.writerow(
            [
                "" if t_sim is None else f"{t_sim:.3f}",
                f"{pos['x']:.6f}",
                f"{pos['y']:.6f}",
                f"{pos['z']:.6f}",
            ]
        )

async def send_and_wait_ack(ws, cmd_payload):
    await ws.send(json.dumps(cmd_payload))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("type") == "event":
            if msg.get("event") == "command.ack" and msg.get("ref_msg_id") == cmd_payload["msg_id"]:
                print("[WS] Ack:", msg.get("detail"))
                return
            if msg.get("event") == "command.error" and msg.get("ref_msg_id") == cmd_payload["msg_id"]:
                raise RuntimeError("Command failed: " + (msg.get("detail") or ""))

async def query_position(ws):
    mid = str(uuid.uuid4())
    q = {"type": "query", "query": "get.position", "target_id": TARGET_ID, "msg_id": mid}
    await ws.send(json.dumps(q))
    route_completed = False
    while True:
        msg = json.loads(await ws.recv())
        # log async events too
        if msg.get("type") == "event":
            if msg.get("event") == "route.complete" and msg.get("target_id") == TARGET_ID:
                print("[WS] Route complete")
                route_completed = True
                # keep waiting for our response; we return position separately
            continue
        if msg.get("type") == "response" and msg.get("msg_id") == mid:
            return msg["result"], msg.get("t_sim"), route_completed

async def handler(ws):
    print("[WS] Unity connected")

    # 1) Send route
    cmd = {
        "type": "command",
        "command": "set.route",
        "target_id": TARGET_ID,
        "msg_id": str(uuid.uuid4()),
        "args": {"waypoints": WAYPOINTS, "speed": SPEED_MPS, "start_immediately": True},
    }
    await send_and_wait_ack(ws, cmd)

    # 2) Poll position while moving (simple demo loop)
    try:
        route_finished = False
        while True:
            pos, t_sim, route_finished = await query_position(ws)
            append_position_to_csv(t_sim, pos)
            print(f"[POS] t={t_sim:7.2f}  x={pos['x']:6.2f}  y={pos['y']:5.2f}  z={pos['z']:6.2f}")
            if route_finished:
                print("[WS] Stopping poll after route completion")
                break
            await asyncio.sleep(1.0 / POLL_HZ)
    except websockets.ConnectionClosed:
        print("[WS] Disconnected")
        return

    print("[WS] Awaiting Unity to close the socket...")
    await ws.wait_closed()
    print("[WS] Connection closed by Unity")

async def main():
    async with websockets.serve(handler, HOST, PORT):
        print(f"[WS] Listening on ws://{HOST}:{PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
