from __future__ import annotations

import logging
from math import sqrt

from src.domain.status_constants import LANDING_PARAMETERS

logger = logging.getLogger(__name__)

TOUCHDOWN_SEGMENT_PURPOSES = {"landing_range_final"}


def _vec3_distance(a: dict, b: dict) -> float:

    return sqrt(
        (float(a["x"]) - float(b["x"])) ** 2
        + (float(a["y"]) - float(b["y"])) ** 2
        + (float(a["z"]) - float(b["z"])) ** 2
    )


def _segment_points(spline: dict) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []

    for entry in spline.get("knotEntries") or []:
        params = entry.get("parameters") or []
        if not params:
            continue

        point = params[0]
        try:
            points.append((
                float(point["x"]),
                float(point["y"]),
                float(point["z"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    return points


def _spline_total_length_units(spline: dict) -> float | None:
    for key in ("lengthUnits", "lengthMeters"):
        try:
            length_units = float(spline.get(key))
        except (AttributeError, TypeError, ValueError):
            length_units = 0.0

        # lengthMeters is a legacy Unity field that currently contains world
        # units. Prefer lengthUnits when Unity sends it.
        if length_units > 0.0:
            return length_units

    points = _segment_points(spline)
    if len(points) < 2:
        return None

    cumulative = _polyline_cumulative_lengths(points)
    return cumulative[-1] if cumulative else None


def _polyline_cumulative_lengths(points: list[tuple[float, float, float]]) -> list[float]:
    cumulative = [0.0]

    for previous, current in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + sqrt(
            (current[0] - previous[0]) ** 2
            + (current[1] - previous[1]) ** 2
            + (current[2] - previous[2]) ** 2
        ))

    return cumulative


def _length_between_t(points: list[tuple[float, float, float]], t_start: float, t_end: float) -> float:
    if len(points) < 2:
        return 0.0

    cumulative = _polyline_cumulative_lengths(points)
    total = cumulative[-1]
    if total <= 0.0:
        return 0.0

    start_t = max(0.0, min(1.0, float(t_start)))
    end_t = max(0.0, min(1.0, float(t_end)))
    return abs(end_t - start_t) * total


def _length_between_t_for_spline(spline: dict, t_start: float, t_end: float) -> float:
    total = _spline_total_length_units(spline)
    if total is None or total <= 0.0:
        return 0.0

    start_t = max(0.0, min(1.0, float(t_start)))
    end_t = max(0.0, min(1.0, float(t_end)))
    return abs(end_t - start_t) * total


def _route_travel_seconds(
        *,
        route_segments: list[dict],
        spline_lookup,
        fallback_kmh: float,
) -> float | None:
    total_seconds = 0.0
    resolved_any = False

    for segment in route_segments:
        spline_name = str(segment.get("name", "") or "")
        spline = spline_lookup(spline_name)
        if not isinstance(spline, dict):
            continue

        length_units = _length_between_t_for_spline(
            spline,
            float(segment.get("t_start", 0.0)),
            float(segment.get("t_end", 1.0)),
        )
        if length_units <= 0.0:
            continue

        resolved_any = True
        profile = segment.get("speed_profile") if isinstance(segment.get("speed_profile"), dict) else {}
        speed_kmh = _segment_schedule_speed_kmh(segment, fallback_kmh)
        speed_mps = max(0.01, speed_kmh * 1000.0 / 3600.0)
        meters = length_units * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT
        segment_seconds = meters / speed_mps
        total_seconds += segment_seconds

        logger.info(
            "[landing_timing] segment=%s length_units=%.3f meters=%.3f target_kmh=%.3f seconds=%.1f",
            spline_name,
            length_units,
            meters,
            speed_kmh,
            segment_seconds,
        )

        if profile.get("purpose") in TOUCHDOWN_SEGMENT_PURPOSES:
            logger.info(
                "[landing_timing] stopping_at_touchdown segment=%s purpose=%s",
                spline_name,
                profile.get("purpose"),
            )
            break

    if not resolved_any:
        return None

    if total_seconds <= 0.0:
        return None

    logger.info("[landing_timing] route_total_seconds=%.1f", total_seconds)

    return total_seconds


def _segment_schedule_speed_kmh(segment: dict, fallback_kmh: float) -> float:
    profile = segment.get("speed_profile")
    if not isinstance(profile, dict):
        return fallback_kmh

    for key in ("schedule_speed_kmh", "target_speed_kmh"):
        try:
            speed_kmh = float(profile.get(key))
        except (TypeError, ValueError):
            continue

        if speed_kmh > 0.0:
            return speed_kmh

    return fallback_kmh


def landing_spawn_lead_seconds(
        *,
        spawn_position: dict,
        airport_position: dict,
        avg_speed_kmh: float = LANDING_PARAMETERS.LANDING_AVG_SPEED_KMH,
        route_segments: list[dict] | None = None,
        spline_lookup = None,
        final_landing_to_stand_seconds: float = LANDING_PARAMETERS.FINAL_LANDING_TO_STAND_SECONDS,
) -> float:
    seconds: float | None = None

    if route_segments and callable(spline_lookup):
        seconds = _route_travel_seconds(
            route_segments=route_segments,
            spline_lookup=spline_lookup,
            fallback_kmh=avg_speed_kmh,
        )

    if seconds is None:
        unity_distance = _vec3_distance(spawn_position, airport_position)
        meters = unity_distance * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT

        speed_mps = max(0.01, avg_speed_kmh * 1000.0 / 3600.0)
        seconds = meters / speed_mps

    seconds += max(0.0, float(final_landing_to_stand_seconds))

    return max(
        LANDING_PARAMETERS.MIN_LANDING_SPAWN_LEAD_SECONDS,
        seconds,
    )
