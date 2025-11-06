from typing import Dict, Tuple, Optional
import uuid

######################## CREATE WAYPOINTS LIST #########################################

def build_waypoints(start_pos: Dict[str, float], WAYPOINT_OFFSETS) -> list[dict[str, float]]:
    """Create absolute waypoints starting from the object's current position."""

    waypoints: list[dict[str, float]] = [
        {"x": start_pos["x"], "y": start_pos["y"], "z": start_pos["z"]}
    ]

    cur_x = start_pos["x"]
    cur_y = start_pos["y"]
    cur_z = start_pos["z"]

    for dx, dy, dz in WAYPOINT_OFFSETS:
        cur_x += dx
        cur_y += dy
        cur_z += dz
        waypoints.append({"x": cur_x, "y": cur_y, "z": cur_z})

    return waypoints

############################# GET POSITION QUERY ##############################################

async def query_position(bus, target_id: str) -> Tuple[Dict[str, float], Optional[float]]:
    mid = str(uuid.uuid4())
    resp = await bus.send_query({"type": "query", "query": "get.position", "target_id": target_id, "msg_id": mid})
    if resp.get("error"):
        raise RuntimeError(f"get.position error for {target_id}: {resp['error']}")
    return resp["result"], resp.get("t_sim")

