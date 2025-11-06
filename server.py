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

TARGETS = ["CUBE_1", "CUBE_2", "CUBE_3"]
CONCURRENCY = 2

WAYPOINT_OFFSETS: list[tuple[float, float, float, int]] = [
    (0.0, 0.0, -30.0, 12),     # +30 Z (climb gently)
    (-110.0, 0.0, 0.0, 18),   # -110 X
    (0.0, 0.0, 120.0, 20),    # +120 Z
    (150.0, 0.0, 0.0, 22),    # +150 X
    (1000.0, 150.0, 0.0, 24) # Decollo
]


def build_waypoints(start_pos: Dict[str, float]) -> list[dict[str, float]]:
    """Create absolute waypoints starting from the object's current position."""

    waypoints: list[dict[str, float]] = [
        {"x": start_pos["x"], "y": start_pos["y"], "z": start_pos["z"]}
    ]

    cur_x = start_pos["x"]
    cur_y = start_pos["y"]
    cur_z = start_pos["z"]

    for dx_total, dy_total, dz_total, steps in WAYPOINT_OFFSETS:
        step_x = dx_total / steps
        step_y = dy_total / steps
        step_z = dz_total / steps
        for _ in range(steps):
            cur_x += step_x
            cur_y += step_y
            cur_z += step_z
            waypoints.append({"x": cur_x, "y": cur_y, "z": cur_z})

    return waypoints
SPEED_MPS = 2.0
POLL_HZ = 5

POS_CSV = Path(__file__).with_name("pos.csv")
ROUTE_LOG_CSV = Path(__file__).with_name("route_log.csv")
SPEED_LOG_CSV = Path(__file__).with_name("speed_log.csv")


def append_position_to_csv(target_id: str, t_sim: Optional[float], pos: Dict[str, float]) -> None:
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
    exists = ROUTE_LOG_CSV.exists()
    with ROUTE_LOG_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "event", "t_host", "t_sim", "ref_msg_id"])
        w.writerow([target_id, event, f"{time.time():.3f}", "" if t_sim is None else f"{t_sim:.3f}", ref_msg_id or ""])

def log_speed_change(target_id: str, cmd_id: str, speed: float, accel_up: Optional[float], accel_down: Optional[float]) -> None:
    exists = SPEED_LOG_CSV.exists()
    with SPEED_LOG_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "t_host", "cmd_id", "speed_mps", "accel_up", "accel_down"])
        w.writerow([target_id, f"{time.time():.3f}", cmd_id, f"{speed:.3f}",
                    "" if accel_up is None else f"{accel_up:.3f}",
                    "" if accel_down is None else f"{accel_down:.3f}"])


class Bus:
    def __init__(self, ws: websockets.WebSocketServerProtocol):
        self.ws = ws
        self.pending_queries: dict[str, asyncio.Future] = {}
        self.pending_acks: dict[str, asyncio.Future] = {}
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self):
        self._reader_task = asyncio.create_task(self._reader())

    async def stop(self):
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def _reader(self):
        async for raw in self.ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            t = msg.get("type")
            if t == "response":
                mid = msg.get("msg_id")
                fut = self.pending_queries.pop(mid, None)
                if fut and not fut.done():
                    fut.set_result(msg)
            elif t == "event":
                ref = msg.get("ref_msg_id")
                fut = self.pending_acks.pop(ref, None) if ref else None
                if fut and not fut.done():
                    fut.set_result(msg)
                else:
                    await self.events.put(msg)

    async def send(self, payload: dict):
        await self.ws.send(json.dumps(payload))

    async def send_query(self, payload: dict) -> dict:
        mid = payload["msg_id"]
        fut = asyncio.get_event_loop().create_future()
        self.pending_queries[mid] = fut
        await self.send(payload)
        return await fut

    async def send_cmd_wait_ack(self, payload: dict) -> dict:
        mid = payload["msg_id"]
        fut = asyncio.get_event_loop().create_future()
        self.pending_acks[mid] = fut
        await self.send(payload)
        return await fut


async def query_position(bus: Bus, target_id: str) -> Tuple[Dict[str, float], Optional[float]]:
    mid = str(uuid.uuid4())
    resp = await bus.send_query({"type": "query", "query": "get.position", "target_id": target_id, "msg_id": mid})
    if resp.get("error"):
        raise RuntimeError(f"get.position error for {target_id}: {resp['error']}")
    return resp["result"], resp.get("t_sim")

async def start_route(
    bus: Bus,
    target_id: str,
    waypoints: list[dict[str, float]],
    speed: float,
    start_t_sim: Optional[float] = None,
) -> str:
    cmd_id = str(uuid.uuid4())
    ack = await bus.send_cmd_wait_ack({
        "type": "command",
        "command": "set.route",
        "target_id": target_id,
        "msg_id": cmd_id,
        "args": {"waypoints": waypoints, "speed": speed},
    })
    if ack.get("event") == "command.error":
        raise RuntimeError(f"set.route failed for {target_id}: {ack.get('detail')}")
    log_route_event(target_id, "start", cmd_id, start_t_sim)
    return cmd_id

async def set_speed(bus: Bus, target_id: str, speed: float, accel_up: Optional[float] = None, accel_down: Optional[float] = None) -> str:
    cmd_id = str(uuid.uuid4())
    args: Dict[str, float] = {"speed": float(speed)}
    if accel_up is not None:   args["accel_up"] = float(accel_up)
    if accel_down is not None: args["accel_down"] = float(accel_down)
    ack = await bus.send_cmd_wait_ack({
        "type": "command",
        "command": "speed.set",
        "target_id": target_id,
        "msg_id": cmd_id,
        "args": args,
    })
    if ack.get("event") == "command.error":
        raise RuntimeError(f"speed.set failed for {target_id}: {ack.get('detail')}")
    log_speed_change(target_id, cmd_id, speed, accel_up, accel_down)
    return cmd_id

async def speed_jitter(bus: Bus, active: Dict[str, dict], *, min_interval=1.5, max_interval=4.0,
                       min_speed=100, max_speed=120,
                       accel_up_rng=(18.0, 20.0), accel_down_rng=(1.0, 2.0)):
    """Background task: randomly tweak speed of a random active target."""
    while True:
        await asyncio.sleep(random.uniform(min_interval, max_interval))
        choices = [t for t in active.keys()]
        if not choices:
            continue
        t_id = random.choice(choices)
        new_speed = random.uniform(min_speed, max_speed)
        up = random.uniform(*accel_up_rng)
        down = random.uniform(*accel_down_rng)
        try:
            await set_speed(bus, t_id, new_speed, accel_up=up, accel_down=down)
            print(f"[{t_id}] speed.set → {new_speed:.2f} m/s (↑{up:.1f} ↓{down:.1f})")
        except Exception as e:
            print(f"[{t_id}] speed.set error: {e}")

async def handler(ws):
    print("[WS] Unity connected")
    bus = Bus(ws)
    await bus.start()

    active: dict[str, dict] = {}   # target_id -> {"cmd_id": str, "last_t_sim": Optional[float]}
    recently_used: Optional[str] = None

    jitter_task = asyncio.create_task(speed_jitter(bus, active))

    try:
        while True:
            # Ensure 2 concurrent cubes
            while len(active) < CONCURRENCY:
                candidates = [t for t in TARGETS if t not in active and t != recently_used] or \
                             [t for t in TARGETS if t not in active] or TARGETS
                target = random.choice(candidates)
                try:
                    start_pos, start_t_sim = await query_position(bus, target)
                    route = build_waypoints(start_pos)
                    cmd_id = await start_route(bus, target, route, SPEED_MPS, start_t_sim)
                except Exception as err:
                    print(f"[WS] Failed to start {target}: {err}")
                    recently_used = target
                    await asyncio.sleep(0)  # yield before retry
                    continue
                active[target] = {"cmd_id": cmd_id, "last_t_sim": start_t_sim}
                recently_used = target
                print(f"[WS] Started {target} at x={start_pos['x']:.2f}, y={start_pos['y']:.2f}, z={start_pos['z']:.2f}")

            # Poll positions concurrently
            poll_tasks = {t: asyncio.create_task(query_position(bus, t)) for t in list(active)}
            done, _ = await asyncio.wait(poll_tasks.values(), timeout=None)
            for t, task in poll_tasks.items():
                if task.done() and not task.cancelled():
                    try:
                        pos, t_sim = task.result()
                        active[t]["last_t_sim"] = t_sim
                        append_position_to_csv(t, t_sim, pos)
                        print(f"[{t}] t={t_sim:7.2f}  x={pos['x']:6.2f}  y={pos['y']:5.2f}  z={pos['z']:6.2f}")
                    except Exception as e:
                        print(f"[{t}] query error: {e}")

            # Drain events; retire finished cubes
            while True:
                try:
                    ev = bus.events.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if ev.get("event") == "route.complete":
                    t_id = ev.get("target_id")
                    if t_id in active:
                        t_sim = ev.get("t_sim", active[t_id].get("last_t_sim"))
                        log_route_event(t_id, "stop", active[t_id]["cmd_id"], t_sim)
                        print(f"[WS] {t_id} complete; freeing slot.")
                        active.pop(t_id, None)

            await asyncio.sleep(1.0 / POLL_HZ)

    except websockets.ConnectionClosed:
        print("[WS] Disconnected")
    finally:
        jitter_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await jitter_task
        await bus.stop()

async def main():
    async with websockets.serve(handler, HOST, PORT):
        print(f"[WS] Listening on ws://{HOST}:{PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    import contextlib
    asyncio.run(main())
