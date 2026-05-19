from sqlalchemy import select
from src.db import models

from src.transport.command_builders import build_start_path_command, build_continue_path_command
from src.domain.status_constants import DEFAULT_PLANE_SPEED

# Now constant speed CHANGE WITH DYNAMIC SPEED

MASTER_SPLINE_NAME = "MasterSpline"
DEPARTURE_SPLINE_NAME = "Spline_Departure"

def get_route_id_for_airplane(*, session, airplane_id: str) -> str | None:
    return session.execute(
        select(models.Airplane.route_id).where(models.Airplane.id == airplane_id)
    ).scalar_one_or_none()


def get_segments_for_route(*, session, route_id: str) -> list | None:
    path = session.get(models.Path, route_id)
    if path is None or not path.spline:
        return None
    return path.spline


def detect_route_kind(segments: list[dict]) -> str:

    # Get splines name from segments
    names = [str(seg.get("name", "")) for seg in segments]

    # Check for departure spline
    if any("Departure" in name for name in names):
        return "departure"

    # Check for parking spline
    if any("Parking" in name for name in names):
        return "parking"

    # Check for landing spline
    if any("Landing" in name or "LongLanding" in name for name in names):
        return "landing"
    
    return "taxi"


def speed_profile_for_segment(*, route_kind: str, segment: dict, index: int, total: int) -> dict:
    name = str(segment.get("name", ""))

    if route_kind == "departure":
        if index == 0:
            return {
                "purpose": "stand_exit",
                "initial_speed_kmh": 0.0,
                "target_speed_kmh": 1.0,
                "acceleration_mps2": 0.15,
                "deceleration_mps2": 0.25,
            }

        if name == "MasterSpline":
            return {
                "purpose": "taxi",
                "initial_speed_kmh": 1.0,
                "target_speed_kmh": 1.5,
                "acceleration_mps2": 0.20,
                "deceleration_mps2": 0.25,
            }

        if name == "Spline_Departure":
            return {
                "purpose": "departure_accel",
                "initial_speed_kmh": 1.5,
                "target_speed_kmh": 5.0,
                "acceleration_mps2": 0.65,
                "deceleration_mps2": 0.30,
            }

    if route_kind == "landing":
        if "Landing" in name:
            return {
                "purpose": "landing_decel",
                "initial_speed_kmh": 2,
                "target_speed_kmh": 0.5,
                "acceleration_mps2": 0.10,
                "deceleration_mps2": 0.35,
            }

        if name == "MasterSpline":
            return {
                "purpose": "taxi_after_landing",
                "initial_speed_kmh": 0.5,
                "target_speed_kmh": 0.25,
                "acceleration_mps2": 0.04,
                "deceleration_mps2": 0.35,
            }

        if index == total - 1:
            return {
                "purpose": "stand_approach",
                "initial_speed_kmh": 0.25,
                "target_speed_kmh": 0.25,
                "acceleration_mps2": 0.03,
                "deceleration_mps2": 0.08,
            }
        
    if route_kind == "parking":

        # PARKING ENTRY SPEED PROFILE
        if "Entry_Parking" in name:
            return {
                "purpose": "parking_entry",
                "initial_speed_kmh": 2.0,
                "target_speed_kmh": 2.0,
                "acceleration_mps2": 0.25,
                "deceleration_mps2": 0.30,
            }
        
        # PARKING LOOP SPEED PROFILE
        if "Parking" in name and "Entry" not in name and "Exit" not in name:
            return {
                "purpose": "parking_loop",
                "initial_speed_kmh": 2.0,
                "target_speed_kmh": 2.0,
                "acceleration_mps2": 0.15,
                "deceleration_mps2": 0.15,
            }
        
        # PARKING EXIT SPEED PROFILE
        if "Exit_Parking" in name:
            return {
                "purpose": "parking_exit",
                "initial_speed_kmh": 2.0,
                "target_speed_kmh": 0.5,
                "acceleration_mps2": 0.25,
                "deceleration_mps2": 0.45,
            }

    return {
        "purpose": "taxi",
        "initial_speed_kmh": 1.0,
        "target_speed_kmh": 1.0,
        "acceleration_mps2": 0.15,
        "deceleration_mps2": 0.20,
    }


DEFAULT_DEPARTURE_HOLD_T = 0.15
DEPARTURE_HOLD_SECONDS = 5.0


def split_departure_segment(segment: dict) -> list[dict]:

    # Get T start and T end
    t_start = float(segment.get("t_start", 0.0))
    t_end = float(segment.get("t_end", 1.0))

    # Get departure hold T from the departure segment
    hold_t = float(segment.get("departure_hold_t", DEFAULT_DEPARTURE_HOLD_T))

    if not (t_start < hold_t < t_end):
        return [segment]
    
    # Create first segment with speed profile (Departure start --> Knot 3)
    first = dict(segment)
    first["t_end"] = hold_t
    first["speed_profile"] = {
        "purpose": "departure_taxi_to_hold",
        "initial_speed_kmh": 5.0,
        "target_speed_kmh": 1.5,
        "acceleration_mps2": 0.3,
        "deceleration_mps2": 0.8,
    }
    first["hold_seconds"] = DEPARTURE_HOLD_SECONDS

    # Create second segment with speed profile (Knot 3 --> Departure Takeoff)
    second = dict(segment)
    second["t_start"] = hold_t
    second["speed_profile"] = {
        "purpose": "departure_roll",
        "initial_speed_kmh": 0.0,
        "target_speed_kmh": 8.0,
        "acceleration_mps2": 0.45,
        "deceleration_mps2": 0.5,
    }

    return [first, second]


def attach_speed_profiles(segments: list[dict]) -> list[dict]:

    # Find route kind (departure / landing) and total segments
    route_kind = detect_route_kind(segments)
    output = []

    for index, segment in enumerate(segments):

        # Retrieve spline name from the segment
        name = str(segment.get("name", ""))

        # For departure spline, split spline for different speed profile
        if route_kind == "departure" and name == DEPARTURE_SPLINE_NAME:
            output.extend(split_departure_segment(segment))
            continue

        # Enrich every segment with corresponding speed profile
        enriched = dict(segment)
        enriched["speed_profile"] = speed_profile_for_segment(
            route_kind=route_kind,
            segment=segment,
            index=index,
            total=len(segments),
        )

        # Append segments to new list
        output.append(enriched)
    
    return output


def detect_motion_mode(segments: list[dict]) -> str:
    names = [str(seg.get("name", "")) for seg in segments]

    if any("Departure" in name for name in names):
        return "departure"

    if any("Landing" in name for name in names):
        return "landing"

    return "taxi"



def make_start_path_command(
    *,
    airplane_id: str,
    flight_id: str | None = None,
    speed: float = DEFAULT_PLANE_SPEED,
    Session=None,
) -> dict | None:
    
    with Session() as session:

        # Get the route linked to the airplane
        route_id = get_route_id_for_airplane(session=session, airplane_id=airplane_id)
        if route_id is None:
            return None
        
        # Get the path from DB corresponding to the route
        segments = get_segments_for_route(session=session, route_id=route_id)
        if not segments:
            return None

        # Enrich spline payloads with speed profiles
        segments = attach_speed_profiles(segments)
        
        # Return START PATH command
        return build_start_path_command(
            airplane_id=airplane_id,
            flight_id=flight_id,
            route_id=route_id,
            segments=segments
        )

def _make_continue_path_command_from_session(*, session, airplane_id: str) -> dict | None:
    route_id = get_route_id_for_airplane(session=session, airplane_id=airplane_id)
    if route_id is None:
        return None
    
    segments = get_segments_for_route(session=session, route_id=route_id)
    if not segments:
        return None
    
    segments = attach_speed_profiles(segments)

    return build_continue_path_command(
        airplane_id=airplane_id,
        route_id=route_id,
        segments=segments,
    )


def make_continue_path_command(*, airplane_id: str, Session=None, session=None) -> dict | None:
    if session is not None:
        return _make_continue_path_command_from_session(
            session=session,
            airplane_id=airplane_id,
        )

    if Session is None:
        return None

    with Session() as local_session:
        return _make_continue_path_command_from_session(
            session=local_session,
            airplane_id=airplane_id,
        )
