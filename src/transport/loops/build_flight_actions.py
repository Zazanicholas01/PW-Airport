from __future__ import annotations

from src.db import db_functions as f
from src.db.actions import DbActions
from src.transport.loops.flight_actions import FlightActions


def build_flight_actions(*, Session) -> FlightActions:
    db = DbActions(Session=Session)

    return FlightActions(
        list_flights_in_sliding_window=f.list_flights_in_sliding_window,
        normalize_flight_type=f.normalize_flight_type,
        assign_airplane_to_departure_flight=f.assign_airplane_to_departure_flight,
        assign_path_to_airplane=f.assign_path_to_airplane,
        create_and_assign_airplane_for_landing_departure=f.create_and_assign_airplane_for_landing_departure,
        mark_landing_departed=f.mark_landing_departed,
        mark_departure_started=f.mark_departure_started,
        reserve_stand_and_link_airplane_for_landing_arrival=f.reserve_stand_and_link_airplane_for_landing_arrival,
        assign_landing_path_for_airplane=f.assign_landing_path_for_airplane,
        get_airplane_prefab=f.get_airplane_prefab,
        count_parked_airplanes=db.count_parked_airplanes,
        generate_debug_flights=db.generate_debug_flights,
    )

