from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable


@dataclass(frozen=True)
class FlightActions:
    list_flights_in_sliding_window: Callable[..., list]
    normalize_flight_type: Callable[[Any], str | None]

    assign_airplane_to_departure_flight: Callable[..., tuple[str, str] | None]
    assign_path_to_airplane: Callable[..., None]

    create_and_assign_airplane_for_landing_departure: Callable[..., str | None]

    mark_landing_departed: Callable[..., None]
    mark_departure_embarking: Callable[..., None]
    mark_departure_started: Callable[..., None]

    reserve_stand_and_link_airplane_for_landing_arrival: Callable[..., str | None]
    assign_landing_path_for_airplane: Callable[..., None]

    get_airplane_prefab: Callable[..., str | None]

    count_parked_airplanes: Callable[[], int]
    generate_debug_flights: Callable[[int, bool, timedelta], None]

