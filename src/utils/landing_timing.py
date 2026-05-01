from __future__ import annotations

from math import sqrt
from src.domain.status_constants import LANDING_PARAMETERS

def _vec3_distance(a: dict, b: dict) -> float:

    return sqrt(
        (float(a["x"]) - float(b["x"])) ** 2
        + (float(a["y"]) - float(b["y"])) ** 2
        + (float(a["z"]) - float(b["z"])) ** 2
    )


def landing_spawn_lead_seconds(
        *,
        spawn_position: dict,
        airport_position: dict,
        avg_speed_kmh: float = LANDING_PARAMETERS.LANDING_AVG_SPEED_KMH,
) -> float:
    
    unity_distance = _vec3_distance(spawn_position, airport_position)
    meters = unity_distance * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT

    speed_mps = max(1.0, avg_speed_kmh * 1000.0 / 3600.0)
    seconds = meters / speed_mps

    return max(
        LANDING_PARAMETERS.MIN_LANDING_SPAWN_LEAD_SECONDS,
        min(LANDING_PARAMETERS.MAX_LANDING_SPAWN_LEAD_SECONDS, seconds),
    )
