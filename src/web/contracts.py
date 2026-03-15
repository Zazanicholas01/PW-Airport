from typing import Any


def make_clock_anchor(*, sim_unix_ms: int, time_scale: float) -> dict[str, Any]:
    return {
        "type": "clock_anchor",
        "sim_unix_ms": sim_unix_ms,
        "time_scale": time_scale,
    }


def make_flight_upsert(flight: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "flight_upsert",
        "flight": flight,
    }


def make_plane_upsert(plane: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "plane_upsert",
        "plane": plane,
    }


def make_log_event(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "log",
        "payload": payload,
    }


def make_snapshot_refresh() -> dict[str, Any]:
    return {
        "type": "snapshot_refresh",
    }
