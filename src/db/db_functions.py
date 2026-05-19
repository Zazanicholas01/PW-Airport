import logging
from src.db import models
from src.utils.mapping import (
    range_for_airplane_model, 
    type_for_airplane_model, 
    landing_source_for_range,
    capacity_for_airplane_model,
)
from src.utils.datetimes import as_utc
from src.utils.standard import normalize_distance, normalize_flight_type, stand_category
from src.utils.geo_direction import (
    direction_for_airport_icao, 
    landing_route_source,
    departure_route_destination
)

from src.domain.status_constants import *

from collections.abc import Callable
from functools import lru_cache

from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, or_, and_, update

from datetime import datetime, timedelta, timezone

from uuid import uuid4


_session_factory: sessionmaker | None = None

def configure_session_factory(Session: sessionmaker) -> None:
    """Inject the SQLAlchemy session factory (recommended at app startup)."""
    global _session_factory
    _session_factory = Session

@lru_cache()
def _fallback_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), future=True)

def _get_session_factory() -> sessionmaker:
    return _session_factory or _fallback_session_factory()


def get_airplane_prefab(*, airplane_id: str) -> str | None:
    """Open session and run query to retrieve the model of an airplane"""

    with _get_session_factory()() as session:
        return session.execute(
            select(models.Airplane.model).where(models.Airplane.id == airplane_id)
        ).scalar_one_or_none()


def link_airplane_to_stand(*, stand_id: str, airplane_id: str) -> None:
    """Link and airplane to a stand"""

    with _get_session_factory()() as session:

        # Get stand from DB
        stand = session.get(models.Stand, stand_id)
        if stand is None:
            logging.warning(f"[db] Stand not found: {stand_id}")
            return
        
        # Link airplane to Stand - airplane_id
        stand.airplane_id = airplane_id
        session.commit()
        logging.info(f"[db] Linked stand {stand_id} -> airplane {airplane_id}")


def unlink_airplane_from_stand(*, stand_id: str, airplane_id: str | None = None) -> None:
    """Unlink an airplane from the stand"""

    with _get_session_factory()() as session:

        # Get stand from DB with sanity check on the airplane to be the same linked
        stand = session.get(models.Stand, stand_id)
        if stand is None:
            logging.warning("[db] Stand not found: %s", stand_id)
            return
        if airplane_id is not None and stand.airplane_id != airplane_id:
            return

        # Release the Stand - airplane_id field
        stand.airplane_id = None
        session.commit()
        logging.info(f"[db] Unlinked stand {stand_id}")


def list_flights_in_sliding_window(*, airport_icao: str, now_utc: datetime, window: timedelta):
    """List all the flights inside the scheduling window"""

    # Get current time and compute the window's upper bound
    now_utc = as_utc(now_utc)
    now_db = now_utc.astimezone(timezone.utc)
    upper = now_db + window

    with _get_session_factory()() as session:
        q = (
            select(models.Flight)
            .where(
                # Every flight that includes the personal airport, both departures and landings
                or_(
                    models.Flight.origin == airport_icao,
                    models.Flight.destination == airport_icao,
                )
            )
            .where(models.Flight.status != FLIGHT_STATUS.COMPLETED) # Excluded Completed Flights
            .where(
                or_(
                    # Unscheduled flights inside sliding window
                    and_(
                        models.Flight.status == FLIGHT_STATUS.UNSCHEDULED,
                        models.Flight.origin == airport_icao,
                        models.Flight.departure_time.is_not(None),
                        models.Flight.departure_time >= now_db,
                        models.Flight.departure_time <= upper,
                    ),

                    # Unscheduled flights on remote airports inside sliding window
                    and_(
                        models.Flight.status == FLIGHT_STATUS.UNSCHEDULED,
                        models.Flight.destination == airport_icao,
                        models.Flight.arrival_time.is_not(None),
                        models.Flight.arrival_time >= now_db,
                        models.Flight.arrival_time <= upper,
                    ),

                    # Any active lifecycle flight stays visible regardless of time.
                    models.Flight.status.in_(LIFECYCLE_STATUSES),
                )
            )
            .order_by(
                models.Flight.departure_time.asc().nulls_last(),
                models.Flight.arrival_time.asc().nulls_last(),
                models.Flight.id.asc(),
            )
        )

        return list(session.scalars(q))


def reserve_stand_for_arrival_flight(*, flight_id: str, flight_type: str | None) -> str | None:
    """Reserve stand for arrival flight based on stand type and plane type"""

    # Set preferences for Cargo flights to prefer C and Passegners flights to prefer P
    preferred = STAND_STATUS.CARGO_CATEGORY if flight_type == FLIGHT_STATUS.CARGO_TYPE else STAND_STATUS.PASSENGERS_CATEGORY
    
    with _get_session_factory()() as session:

        # Get flight and sanity check
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return None

        # Get all stands and filter candidates to only available stands
        stands = list(session.scalars(select(models.Stand)))
        candidates = [
            s for s in stands
            if getattr(s, "status", None) not in STAND_STATUS.UNAVAILABLE
        ]
        if not candidates:
            return None

        # Filter also candidates with the preferred type
        preferred_stands = [s for s in candidates if stand_category(getattr(s, "id", None)) == preferred]

        # Choose first stand with preferred type if present, FALLBACK to 'O' stands
        if preferred_stands:
            chosen = preferred_stands[0]
        else:
            o_stands = [s for s in candidates if stand_category(getattr(s, "id", None)) == "O"]
            if not o_stands:
                return None
            chosen = o_stands[0]
        
        # Update stand and flight to status Reserved
        session.execute(
            update(models.Stand)
            .where(models.Stand.id == chosen.id)
            .values(status=FLIGHT_STATUS.STAND_RESERVED)
        )
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status=STAND_STATUS.RESERVED)
        )
        session.commit()
        return chosen.id
        

def assign_airplane_to_departure_flight(*, flight_id: str, required_type: str | None) -> tuple[str, str] | None:
    """Assign airplane to departure flight"""

    with _get_session_factory()() as session:

        # Get flight from ID and sanity check
        flight = session.get(models.Flight, flight_id)
        if flight is None or flight.airplane_id is not None:
            return None
        
        # Derive required range from destination Airport's distance field
        required_range: str | None = None
        destination_icao = getattr(flight, "destination", None)
        if isinstance(destination_icao, str) and destination_icao:
            dest_airport = session.get(models.Airport, destination_icao)
            if dest_airport is not None:
                required_range = normalize_distance(getattr(dest_airport, "distance", None))

        # Query for Parked airplanes that are currently linked to a stand
        q = (
            select(models.Airplane.id, models.Stand.id)
            .join(models.Stand, models.Stand.airplane_id == models.Airplane.id)
            .where(models.Airplane.status == AIRPLANE_STATUS.PARKED)
        )
        if required_type is not None:
            q = q.where(models.Airplane.type == required_type)
        if required_range is not None:
            q = q.where(models.Airplane.range == required_range)

        # Execute the query
        row = session.execute(q).first()
        if row is None:
            return None

        # Derive airplane, stand and airline code
        airplane_id, stand_id = row
        airline_code = getattr(flight, "airline_code", None)

        # Update airplane to Reserved and flight to Scheduled
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(status=AIRPLANE_STATUS.RESERVED, airline_code=airline_code)
        )
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(airplane_id=airplane_id, status=FLIGHT_STATUS.SCHEDULED)
        )
        session.commit()
        return airplane_id, stand_id


def create_and_assign_airplane_for_landing_departure(
        *, flight_id: str,
        prefab_picker: Callable[[str | None, str | None], str | None] | None = None) -> str | None:
    """Create and assign airplane for landing departure"""

    with _get_session_factory()() as session:

        # Get flight and sanity check (Unscheduled and not an airplane already linked)
        flight = session.get(models.Flight, flight_id)
        if flight is None or flight.airplane_id is not None or getattr(flight, "status", None) != FLIGHT_STATUS.UNSCHEDULED:
            return None
        
        # Get flight type with naming convention enforcing
        flight_type = normalize_flight_type(getattr(flight, "tipo", None))

        # Derive required range from Airport's distance field
        required_range: str | None = None
        origin_icao = getattr(flight, "origin", None)
        if isinstance(origin_icao, str) and origin_icao:
            origin_airport = session.get(models.Airport, origin_icao)
            if origin_airport is not None:
                required_range = normalize_distance(getattr(origin_airport, "distance", None))
        
        # Call Prefab Picker function to retrieve a prefab name
        prefab_name = prefab_picker(flight_type, required_range) if prefab_picker else None

        capacity = 120 # Default

        # If a prefab is chosen, use mapping helpers to find type & range of the model
        if prefab_name:
            try:
                flight_type = type_for_airplane_model(prefab_name)
                required_range = range_for_airplane_model(prefab_name)
                capacity = capacity_for_airplane_model(prefab_name)
            except ValueError:
                prefab_name = None


        # Generate random UUID string and create record of the Airplane following models.Airplane
        airplane_id = str(uuid4())
        airplane = models.Airplane(
            id=airplane_id,
            type=flight_type or AIRPLANE_STATUS.PASSEGNERS_TYPE,
            range=required_range or AIRPLANE_STATUS.RANGE_MEDIUM,
            model=prefab_name,
            capacity=capacity,
            status=AIRPLANE_STATUS.SCHEDULED,
            speed=0.0,
            fuel_level=1.0,
            maintenance=False,
            airline_code=getattr(flight, "airline_code", None),
            route_id=None,
        )
        session.add(airplane)

        # Update flight to Scheduled status
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(airplane_id=airplane_id, status=FLIGHT_STATUS.SCHEDULED)
        )
        session.commit()

        # Logging and return
        logging.info(
            "[db] landing_dep: created airplane_id=%s type=%s range=%s and linked to flight_id=%s (status=Scheduled)",
            airplane_id, airplane.type, airplane.range, flight_id
        )
        return airplane_id
    

def reserve_stand_and_link_airplane_for_landing_arrival(*, flight_id: str) -> str | None:
    """Reserve stand and link airplane for landing arrival"""

    with _get_session_factory()() as session:

        # Get flight from DB
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            logging.warning("[db] landing_arr: flight not found flight_id=%s", flight_id)
            return None
        
        # Get airplane_id from Flight and check status equal to Lan_Ongoing
        airplane_id = getattr(flight, "airplane_id", None)
        if not isinstance(airplane_id, str) or not airplane_id:
            return None
        if getattr(flight, "status", None) != FLIGHT_STATUS.LAN_ONGOING:
            return None
        
        # Determine preferred stand category and filter to currently available stands
        flight_type = normalize_flight_type(getattr(flight, "tipo", None))
        preferred = STAND_STATUS.CARGO_CATEGORY if flight_type == FLIGHT_STATUS.CARGO_TYPE else STAND_STATUS.PASSENGERS_CATEGORY

        stands = list(session.scalars(select(models.Stand)))
        candidates = [s for s in stands if getattr(s, "status", None) not in STAND_STATUS.UNAVAILABLE]

        # Small helper to apply stand category retrieving function
        def cat(s) -> str | None:
            return stand_category(getattr(s, "type", None))

        # Filter candidates on preferred stands and choose first, FALLABCK to 'O' stands if none available
        preferred_stands = [s for s in candidates if cat(s) == preferred]
        chosen = preferred_stands[0] if preferred_stands else None
        if chosen is None:
            o_stands = [s for s in candidates if cat(s) == "O"]
            if not o_stands:
                return None
            chosen = o_stands[0]
        
        # Update stand to status Reserved
        session.execute(
            update(models.Stand)
            .where(models.Stand.id == chosen.id)
            .values(status=STAND_STATUS.RESERVED, airplane_id=airplane_id)
        )

        # Update Flight to status Landing
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status=FLIGHT_STATUS.LANDING)
        )

        # Update Airplane to status Reserved
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(status=AIRPLANE_STATUS.RESERVED)
        )
        session.commit()
        return chosen.id


def mark_landing_departed(*, flight_id: str) -> None:
    """Mark landing departed"""

    with _get_session_factory()() as session:

        # Get flight from DB
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return

        # Get airplane_id from flight and update flight status to Lan_Ongoing
        airplane_id = getattr(flight, "airplane_id", None)
        if not isinstance(airplane_id, str) or not airplane_id:
            logging.warning("[db] landing_departed skipped flight_id=%s because no airplane is linked", flight_id)
            return

        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status=FLIGHT_STATUS.LAN_ONGOING)
        )

        # If airplane exists, update status to InFlight
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(status=AIRPLANE_STATUS.IN_FLIGHT)
        )
        session.commit()


def mark_departure_embarking(*, flight_id: str) -> None:
    """Mark an outbound departure as embarking"""

    with _get_session_factory()() as session:
        
        # Get flight from DB
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return
        
        # Get airplane_id from the flight
        airplane_id = getattr(flight, "airplane_id", None)

        # Update Flight status to Embarking
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status=FLIGHT_STATUS.EMBARKING)
        )

        # Update airplane status to Embarking
        if isinstance(airplane_id, str):
            session.execute(
                update(models.Airplane)
                .where(models.Airplane.id == airplane_id)
                .values(status=AIRPLANE_STATUS.EMBARKING)
            )
        
        session.commit()
                

def mark_departure_started(*, flight_id: str) -> None:
    """Mark an outbound departure as started"""

    with _get_session_factory()() as session:

        # Get flight from DB
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return
        
        # Get airplane from flight
        airplane_id = getattr(flight, "airplane_id", None)

        # Update flight status from Scheduled --> Departing
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status=FLIGHT_STATUS.DEPARTING)
        )

        # If airplane exists, update airplane status from Parked --> Departing
        if isinstance(airplane_id, str):
            session.execute(
                update(models.Airplane)
                .where(models.Airplane.id == airplane_id)
                .values(status=AIRPLANE_STATUS.DEPARTING)
            )
        
        session.commit()


def assign_path_to_airplane(*, airplane_id: str, source: str, destination: str) -> int | None:
    """Assign path to airplane"""

    with _get_session_factory()() as session:

        # Retrieve path ID by source and destination
        path_id = session.execute(
            select(models.Path.id)
            .where(models.Path.source == source)
            .where(models.Path.destination == destination)
        ).scalar_one_or_none()

        # Sanity check on path ID
        if path_id is None:
            logging.warning("[db] path not found")
            return None
        
        # Update airplane's route_id field with the path
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(route_id=path_id)
        )
        session.commit()

        # Logging and return
        logging.info("[db] path assigned airplane_id=%s route_id=%s (%s -> %s)", airplane_id, path_id, source, destination)
        return path_id


def assign_landing_path_for_airplane(*, airplane_id: str, stand_id: str) -> int | None:
    """Assign landing path for airplane"""

    with _get_session_factory()() as session:

        # Get airplane and sanity check
        airplane = session.get(models.Airplane, airplane_id)
        if airplane is None:
            return None
        
        # Get landing spline based on airplane range
        source = landing_source_for_range(getattr(airplane, "range", None))

        # Get path ID based on source and destination
        path_id = session.execute(
            select(models.Path.id)
            .where(models.Path.source == source)
            .where(models.Path.destination == stand_id)
        ).scalar_one_or_none()

        # Sanity check on path ID
        if path_id is None:
            logging.warning("[db] landing path not found source=%s destination=%s", source, stand_id)
            return None
        
        # Update airplane's route_id based on range
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(route_id=path_id)
        )
        session.commit()

        # Logging and return
        logging.info("[db] landing path assigned airplane_id=%s route_id=%s (%s -> %s)", airplane_id, path_id, source, stand_id)
        return path_id

def landing_route_source_for_airplane(session, airplane_id: str) -> str | None:
    
    # Retrieve airplane from DB
    airplane = session.get(models.Airplane, airplane_id)
    if airplane is None:
        return None
    
    # Assign Long / Medium / Short based on airplane range
    landing_id = landing_source_for_range(getattr(airplane, "range", None))
    return f"{LANDING_ROUTE_SPLINE}_{landing_id}"


def parking_exit_source_for_airplane(session, airplane_id: str, parking_n: int) -> str | None:

    # Retrieve airplane from DB
    airplane = session.get(models.Airplane, airplane_id)
    if airplane is None:
        return None
    
    # Assign Long / Medium / Short based on airplane range
    landing_id = landing_source_for_range(getattr(airplane, "range", None))
    return f"{PARKING_PREFIX}{parking_n}_{landing_id}"


def assign_arrival_route_or_parking(*, flight_id: str) -> dict | None:
    """
    Decide what an arriving plane should do:
    - direct land if stand is available
    - enter parking if no stand is available
    - delay flight if no parking is available

    Returns:
        {"decisions": LANDING_ROUTE_DECISION.LAND, "stand_id": "...", "route_id": 1}
        {"decision": LANDING_ROUTE_DECISION.PARKING, "parking_n": 1, "route_id": 2}
        {"decision": LANDING_ROUTE_DECISION.DELAYED}
        None on invalid flight
    """

    with _get_session_factory()() as session:

        # Retrieve flight from DB
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return None
        
        # Retrieve airplane linked to that flight
        airplane_id = getattr(flight, "airplane_id", None)
        if not isinstance(airplane_id, str) or not airplane_id:
            return None

        # Sanity check on status to be LAN_ONGOING
        if getattr(flight, "status", None) != FLIGHT_STATUS.LAN_ONGOING:
            return None

        # Normalize flight type (Cargo / Passeggeri)
        flight_type = normalize_flight_type(getattr(flight, "tipo", None))
        preferred = (
            STAND_STATUS.CARGO_CATEGORY
            if flight_type == FLIGHT_STATUS.CARGO_TYPE
            else STAND_STATUS.PASSENGERS_CATEGORY
        )

        # Helper function to return the stand category
        def cat(s) -> str | None:
            return stand_category(getattr(s, "type", None))
        
        # Stand decision logic
        stands = list(session.scalars(select(models.Stand)))
        candidates = [s for s in stands if getattr(s, "status", None) not in STAND_STATUS.UNAVAILABLE]

        preferred_stands = [s for s in candidates if cat(s) == preferred]
        chosen_stand = preferred_stands[0] if preferred_stands else None

        if chosen_stand is None:
            o_stands = [s for s in candidates if cat(s) == "O"]
            chosen_stand = o_stands[0] if o_stands else None
        
        # 1. STAND AVAILABLE CASE
        if chosen_stand is not None:
            source = landing_route_source_for_flight(session, flight, airplane_id)
            if source is None:
                return
            
            path_id = session.execute(
                select(models.Path.id)
                .where(models.Path.source == source)
                .where(models.Path.destination == chosen_stand.id)
            ).scalar_one_or_none()

            if path_id is None:
                logging.warning("[db] direct landing path not found source=%s destination=%s", source, chosen_stand.id)
                return None

            chosen_stand.status = STAND_STATUS.RESERVED
            chosen_stand.airplane_id = airplane_id

            airplane = session.get(models.Airplane, airplane_id)
            if airplane is not None:
                airplane.status = AIRPLANE_STATUS.RESERVED
                airplane.route_id = path_id
            
            flight.status = FLIGHT_STATUS.LANDING

            session.commit()
            return {
                "decision": LANDING_ROUTE_DECISION.LAND,
                "stand_id": chosen_stand.id,
                "route_id": path_id,
            }
        
        # Find available parkings in DB
        parking = session.execute(
            select(models.ParkingSpot)
            .where(models.ParkingSpot.status == STAND_STATUS.AVAILABLE)
            .where(models.ParkingSpot.airplane_id.is_(None))
            .order_by(models.ParkingSpot.id)
        ).scalars().first()

        # 2. PARKING CASE
        if parking is not None:
            parking.status = STAND_STATUS.RESERVED
            parking.airplane_id = airplane_id

            direction = direction_for_airport_icao(getattr(flight, "origin", None))

            if direction is None:
                source = LANDING_ROUTE_SPLINE
            else:
                source = f"{LANDING_ROUTE_SPLINE}_{direction.value}"

            path_id = session.execute(
                select(models.Path.id)
                .where(models.Path.source == source)
                .where(models.Path.destination == f"{PARKING_PREFIX}{parking.spline}")
            ).scalar_one_or_none()

            if path_id is None:
                logging.warning(
                    "[db] parking entry path not found source=%s parking=%s flight_id=%s",
                    source,
                    parking.spline,
                    flight_id,
                )
                return None

            airplane = session.get(models.Airplane, airplane_id)
            if airplane is not None:
                airplane.status = AIRPLANE_STATUS.RESERVED
                airplane.route_id = path_id
            
            flight.status = FLIGHT_STATUS.LANDING

            session.commit()
            return {
                "decision": LANDING_ROUTE_DECISION.PARKING,
                "parking_n": parking.spline,
                "route_id": path_id,
            }
        
        # 3. DELAY 15 MINUTES ON ARRIVAL
        flight.arrival_time = flight.arrival_time + timedelta(minutes=15)
        session.commit()

        return {"decision": LANDING_ROUTE_DECISION.DELAYED}


def landing_route_source_for_flight(session, flight, airplane_id: str) -> str | None:

    # Retrieve airplane from DB
    airplane = session.get(models.Airplane, airplane_id)
    if airplane is None:
        return None
    
    # Get airplane range and direction based on remote airport
    landing_id = landing_source_for_range(getattr(airplane, "range", None))
    direction = direction_for_airport_icao(getattr(flight, "origin", None))

    if direction is None:
        return f"{LANDING_ROUTE_SPLINE}_{landing_id}"
    
    return landing_route_source(direction, landing_id)


def departure_route_destination_for_flight(flight) -> str:

    direction = direction_for_airport_icao(getattr(flight, "destination", None))

    if direction is None:
        return DEPARTURE_SPLINE
    
    return departure_route_destination(direction)


def assign_departure_path_for_flight(
    *,
    flight_id: str,
    airplane_id: str,
    stand_id: str,
) -> int | None:
    
    with _get_session_factory()() as session:

        # Retrieve flight from DB
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return None
        
        # Find departure route for the destination
        destination = departure_route_destination_for_flight(flight)

        # Retrieve path from DB
        path_id = session.execute(
            select(models.Path.id)
            .where(models.Path.source == stand_id)
            .where(models.Path.destination == destination)
        ).scalar_one_or_none()

        if path_id is None:
            logging.warning(
                "[db] departure path not found source=%s destination=%s flight_id=%s",
                stand_id,
                destination,
                flight_id,
            )
            return None
        
        # Update Airplane's Route
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(route_id=path_id)
        )
        session.commit()

        logging.info(
            "[db] directional departure path assigned airplane_id=%s route_id=%s (%s -> %s)",
            airplane_id,
            path_id,
            stand_id,
            destination,
        )

        return path_id
