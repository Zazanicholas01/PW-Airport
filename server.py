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

from waypoints import build_waypoints, query_position
from save_csv import log_speed_change, log_route_event, append_position_to_csv
from bus import Bus

################################# CONSTANTS DEFINITION #################################

HOST = "0.0.0.0"
PORT = 8765

TARGETS = ["CUBE_1", "CUBE_2", "CUBE_3"]
CONCURRENCY = 2

WAYPOINT_OFFSETS: list[tuple[float, float, float]] = [
    # Straight +Z (total ≈ +20 Z before the first curve)
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    (0.0, 0.0, -2.0),
    # Curve between +30Z and -110X (radius ~10, 9×10° steps)
    (-0.151922, 0.0, -1.736482),
    (-0.451151, 0.0, -1.683720),
    (-0.736672, 0.0, -1.579799),
    (-0.999810, 0.0, -1.427876),
    (-1.232568, 0.0, -1.232568),
    (-1.427876, 0.0, -0.999810),
    (-1.579799, 0.0, -0.736672),
    (-1.683720, 0.0, -0.451151),
    (-1.736482, 0.0, -0.151922),
    # Straight -X (total -100 X after the curve contributions)
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    # Curve between -110X and +120Z
    (-1.736482, 0.0, 0.151922),
    (-1.683720, 0.0, 0.451151),
    (-1.579799, 0.0, 0.736672),
    (-1.427876, 0.0, 0.999810),
    (-1.232568, 0.0, 1.232568),
    (-0.999810, 0.0, 1.427876),
    (-0.736672, 0.0, 1.579799),
    (-0.451151, 0.0, 1.683720),
    (-0.151922, 0.0, 1.736482),
    # Straight +Z (total +100 Z)
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    (0.0, 0.0, 5.0),
    # Curve between +120Z and +150X
    (0.151922, 0.0, 1.736482),
    (0.451151, 0.0, 1.683720),
    (0.736672, 0.0, 1.579799),
    (0.999810, 0.0, 1.427876),
    (1.232568, 0.0, 1.232568),
    (1.427876, 0.0, 0.999810),
    (1.579799, 0.0, 0.736672),
    (1.683720, 0.0, 0.451151),
    (1.736482, 0.0, 0.151922),
    # Straight +X (total +150 X)
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (5.0, 1.0, 0.0),
    (500.0, 150.0, 0.0)
]

SPEED_MPS = 20.0
POLL_HZ = 5

POS_CSV = Path(__file__).with_name("pos.csv")
ROUTE_LOG_CSV = Path(__file__).with_name("route_log.csv")
SPEED_LOG_CSV = Path(__file__).with_name("speed_log.csv")

######################## SET / START ROUTE COMMAND ##############################################

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

############################ SPEED SET COMMAND ################################################

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
                       min_speed=700, max_speed=900,
                       accel_up_rng=(50.0, 70.0), accel_down_rng=(1.0, 2.0)):
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

################################## HANDLE CONCURRENCY & EVENTS ##############################

async def handler(ws):

    print("[WS] Unity connected")
    bus = Bus(ws)
    await bus.start()

    active: dict[str, dict] = {}   # target_id -> {"cmd_id": str, "last_t_sim": Optional[float]}
    recently_used: Optional[str] = None

    jitter_task = asyncio.create_task(speed_jitter(bus, active))

    try:
        while True:
            
            ################# ENSURE 2 CONCURRENT EVENTS #################################à

            while len(active) < CONCURRENCY:

                candidates = [t for t in TARGETS if t not in active and t != recently_used] or \
                             [t for t in TARGETS if t not in active] or TARGETS
                target = random.choice(candidates)

                try:
                    start_pos, start_t_sim = await query_position(bus, target)
                    route = build_waypoints(start_pos, WAYPOINT_OFFSETS)
                    cmd_id = await start_route(bus, target, route, SPEED_MPS, start_t_sim)

                except Exception as err:
                    print(f"[WS] Failed to start {target}: {err}")
                    recently_used = target
                    await asyncio.sleep(0)  # yield before retry
                    continue

                active[target] = {"cmd_id": cmd_id, "last_t_sim": start_t_sim}
                recently_used = target
                print(f"[WS] Started {target} at x={start_pos['x']:.2f}, y={start_pos['y']:.2f}, z={start_pos['z']:.2f}")

            ################# POLL POSITIONS #########################################

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

            ################# ROUTE COMPLETE COMMAND ####################################

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
