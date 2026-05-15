from __future__ import annotations

from math import sqrt

from src.domain.status_constants import LANDING_PARAMETERS
from src.path_commands import attach_speed_profiles


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
    try:
        length_meters = float(spline.get("lengthMeters"))
    except (AttributeError, TypeError, ValueError):
        length_meters = 0.0

    if length_meters > 0.0:
        return length_meters / LANDING_PARAMETERS.METERS_PER_UNITY_UNIT

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


def _segment_speed_mps(segment: dict, fallback_kmh: float) -> float:
    profile = segment.get("speed_profile") or {}

    initial_kmh = float(profile.get("initial_speed_kmh", fallback_kmh))
    target_kmh = float(profile.get("target_speed_kmh", fallback_kmh))
    effective_kmh = max(0.5, target_kmh if target_kmh > 0.0 else initial_kmh)

    return effective_kmh * 1000.0 / 3600.0


def _profile_params(segment: dict, fallback_kmh: float) -> tuple[float, float, float]:
    profile = segment.get("speed_profile") or {}

    initial_kmh = float(profile.get("initial_speed_kmh", fallback_kmh))
    target_kmh = float(profile.get("target_speed_kmh", fallback_kmh))
    initial_mps = max(0.0, initial_kmh * 1000.0 / 3600.0)
    target_mps = max(0.0, target_kmh * 1000.0 / 3600.0)

    accel = float(profile.get("acceleration_mps2", 0.1))
    decel = float(profile.get("deceleration_mps2", 0.1))
    rate = max(0.01, accel if initial_mps < target_mps else decel)

    return initial_mps, target_mps, rate


def _time_for_distance_with_profile(
        *,
        distance_m: float,
        initial_mps: float,
        target_mps: float,
        rate_mps2: float,
) -> tuple[float, float]:
    distance = max(0.0, distance_m)
    current = max(0.0, initial_mps)
    target = max(0.0, target_mps)
    rate = max(0.01, rate_mps2)

    if distance <= 0.0:
        return 0.0, current

    if abs(current - target) < 1e-6:
        speed = max(0.1, target)
        return distance / speed, target

    delta_speed = target - current
    time_to_target = abs(delta_speed) / rate
    distance_to_target = ((current + target) / 2.0) * time_to_target

    if distance <= distance_to_target:
        if delta_speed > 0.0:
            # distance = v0*t + 0.5*a*t^2
            discriminant = max(0.0, current * current + 2.0 * rate * distance)
            time_needed = (-current + sqrt(discriminant)) / rate
            final_speed = current + rate * time_needed
            return time_needed, final_speed

        # distance = v0*t - 0.5*a*t^2
        discriminant = max(0.0, current * current - 2.0 * rate * distance)
        time_needed = (current - sqrt(discriminant)) / rate
        final_speed = max(target, current - rate * time_needed)
        return time_needed, final_speed

    cruise_speed = max(0.1, target)
    cruise_distance = distance - distance_to_target
    return time_to_target + (cruise_distance / cruise_speed), target


def _route_travel_seconds(
        *,
        route_segments: list[dict],
        spline_lookup,
        fallback_kmh: float,
) -> float | None:
    enriched_segments = attach_speed_profiles(route_segments)
    total_seconds = 0.0
    resolved_any = False
    current_speed_mps = 0.0

    for index, segment in enumerate(enriched_segments):
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
        meters = length_units * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT
        profile_initial_mps, target_mps, rate_mps2 = _profile_params(segment, fallback_kmh)

        if index == 0 or current_speed_mps <= 0.0:
            initial_mps = profile_initial_mps
        else:
            initial_mps = current_speed_mps

        segment_seconds, current_speed_mps = _time_for_distance_with_profile(
            distance_m=meters,
            initial_mps=initial_mps,
            target_mps=target_mps,
            rate_mps2=rate_mps2,
        )
        total_seconds += segment_seconds

    if not resolved_any:
        return None

    return total_seconds


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

        speed_mps = max(1.0, avg_speed_kmh * 1000.0 / 3600.0)
        seconds = meters / speed_mps

    seconds += max(0.0, float(final_landing_to_stand_seconds))

    return max(
        LANDING_PARAMETERS.MIN_LANDING_SPAWN_LEAD_SECONDS,
        seconds,
    )
