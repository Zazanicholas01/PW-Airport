import logging
from src.db import models
from src.utils.mapping import range_for_airplane_model, type_for_airplane_model

from collections.abc import Callable

from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, or_, and_, update

from datetime import datetime, timedelta, timezone

from uuid import uuid4

_engine = get_engine()
Session = sessionmaker(bind=_engine, future=True)

def link_airplane_to_stand(*, stand_id: str, airplane_id: str) -> None:
    with Session() as session:
        stand = session.get(models.Stand, stand_id)
        if stand is None:
            logging.warning("[db] Stand not found: %s", stand_id)
            return
        stand.airplane_id = airplane_id
        session.commit()
        logging.info("[db] Linked stand %s -> airplane %s", stand_id, airplane_id)

def unlink_airplane_from_stand(*, stand_id: str, airplane_id: str | None = None) -> None:
    with Session() as session:
        stand = session.get(models.Stand, stand_id)
        if stand is None:
            logging.warning("[db] Stand not found: %s", stand_id)
            return
        if airplane_id is not None and stand.airplane_id != airplane_id:
            return
        stand.airplane_id = None
        session.commit()
        logging.info("[db] Unlinked stand %s", stand_id)

def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def list_flights_in_sliding_window(*, airport_icao: str, now_utc: datetime, window: timedelta):
    now_utc = _as_utc(now_utc)
    now_db = now_utc.astimezone(timezone.utc)
    upper = now_db + window

    with Session() as session:
        q = (
            select(models.Flight)
            .where(models.Flight.airplane_id.is_(None))
            .where(
                or_(
                    # DEPARTURE
                    and_(
                        models.Flight.origin == airport_icao,
                        models.Flight.status == "Unscheduled",
                        models.Flight.departure_time.is_not(None),
                        models.Flight.departure_time <= upper,
                    ),
                    # ARRIVAL
                    and_(
                        models.Flight.destination == airport_icao,
                        models.Flight.status == "Unscheduled",
                        models.Flight.departure_time.is_not(None),
                        models.Flight.departure_time <= now_db,
                    ),
                )
            )
        )
        base = list(session.scalars(q))

        q2 = (
            select(models.Flight)
            .where(models.Flight.destination == airport_icao)
            .where(models.Flight.status == "Ongoing")
            .where(models.Flight.airplane_id.is_not(None))
            .where(models.Flight.arrival_time.is_not(None))
            .where(models.Flight.arrival_time <= upper)
        )
        base.extend(list(session.scalars(q2)))
        return base

def normalize_flight_type(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if "cargo" in v or "merce" in v:
        return "Cargo"
    if "passeg" in v:
        return "Passengers"
    return value

def normalize_distance(value: str | None) -> str | None:
    if value is None:
        return None
    
    v = value.strip().lower()
    if not v:
        return None
    if "cort" in v:
        return "Short"
    if "medi" in v:
        return "Medium"
    if "lung" in v:
        return "Long"
    return value

def stand_category(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v.startswith("p") or "passeg" in v:
        return "P"
    if v.startswith("c") or "cargo" in v or "merce" in v:
        return "C"
    if v.startswith("o") or "other" in v or "altro" in v:
        return "O"
    return None

def reserve_stand_for_arrival_flight(*, flight_id: str, flight_type: str | None, free_status: str = "Available", reserved_status: str = "Reserved") -> str | None:
    preferred = "C" if flight_type == "Cargo" else "P"
    
    with Session() as session:
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            return None
        
        unavailable_statuses = {"Occupied", "Reserved"}

        stands = list(session.scalars(select(models.Stand)))
        candidates = [
            s for s in stands
            if getattr(s, "status", None) not in unavailable_statuses
        ]
        if not candidates:
            return None

        preferred_stands = [s for s in candidates if stand_category(getattr(s, "id", None)) == preferred]
        if preferred_stands:
            chosen = preferred_stands[0]
        else:
            o_stands = [s for s in candidates if stand_category(getattr(s, "id", None)) == "O"]
            if not o_stands:
                return None
            chosen = o_stands[0]
        
        session.execute(
            update(models.Stand)
            .where(models.Stand.id == chosen.id)
            .values(status=reserved_status)
        )
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status="StandReserved")
        )
        session.commit()
        return chosen.id
        

def assign_airplane_to_departure_flight(*, flight_id: str, required_type: str | None) -> tuple[str, str] | None:
    with Session() as session:
        flight = session.get(models.Flight, flight_id)
        if flight is None or flight.airplane_id is not None:
            return None
        
        required_range: str | None = None
        destination_icao = getattr(flight, "destination", None)
        if isinstance(destination_icao, str) and destination_icao:
            dest_airport = session.get(models.Airport, destination_icao)
            if dest_airport is not None:
                required_range = normalize_distance(getattr(dest_airport, "distance", None))

        q = (
            select(models.Airplane.id, models.Stand.id)
            .join(models.Stand, models.Stand.airplane_id == models.Airplane.id)
            .where(models.Airplane.status == "Parked")
        )
        if required_type is not None:
            q = q.where(models.Airplane.type == required_type)
        if required_range is not None:
            q = q.where(models.Airplane.range == required_range)

        row = session.execute(q).first()
        if row is None:
            return None

        airplane_id, stand_id = row
        airline_code = getattr(flight, "airline_code", None)

        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(status="Reserved", airline_code=airline_code)
        )
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(airplane_id=airplane_id, status="Scheduled")
        )
        session.commit()
        return airplane_id, stand_id
    
def create_and_assign_airplane_for_landing_departure(
        *, flight_id: str,
        prefab_picker: Callable[[str | None, str | None], str | None] | None = None) -> str | None:
    with Session() as session:
        flight = session.get(models.Flight, flight_id)
        if flight is None or flight.airplane_id is not None or getattr(flight, "status", None) != "Unscheduled":
            return None
        
        flight_type = normalize_flight_type(getattr(flight, "tipo", None))

        required_range: str | None = None
        origin_icao = getattr(flight, "origin", None)
        if isinstance(origin_icao, str) and origin_icao:
            origin_airport = session.get(models.Airport, origin_icao)
            if origin_airport is not None:
                required_range = normalize_distance(getattr(origin_airport, "distance", None))
        
        prefab_name = prefab_picker(flight_type, required_range) if prefab_picker else None

        if prefab_name:
            try:
                flight_type = type_for_airplane_model(prefab_name)
                required_range = range_for_airplane_model(prefab_name)
            except ValueError:
                prefab_name = None

        airplane_id = str(uuid4())
        airplane = models.Airplane(
            id=airplane_id,
            type=flight_type or "Passengers",
            range=required_range or "Medium",
            model=prefab_name,
            capacity=100,
            status='InFlight',
            speed=0.0,
            fuel_level=1.0,
            maintenance=False,
            airline_code=getattr(flight, "airline_code", None),
            route_id=None,
        )
        session.add(airplane)

        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(airplane_id=airplane_id, status="Ongoing")
        )
        session.commit()

        logging.info(
            "[db] landing_dep: created airplane_id=%s type=%s range=%s and linked to flight_id=%s (status=Ongoing)",
            airplane_id, airplane.type, airplane.range, flight_id
        )
        return airplane_id
    
def reserve_stand_and_link_airplane_for_landing_arrival(*, flight_id: str) -> str | None:
    with Session() as session:
        flight = session.get(models.Flight, flight_id)
        if flight is None:
            logging.warning("[db] landing_arr: flight not found flight_id=%s", flight_id)

            return None
        airplane_id = getattr(flight, "airplane_id", None)
        if not isinstance(airplane_id, str) or not airplane_id:
            return None
        if getattr(flight, "status", None) != "Ongoing":
            return None
        
        flight_type = normalize_flight_type(getattr(flight, "tipo", None))
        preferred = "C" if flight_type == "Cargo" else "P"
        unavailable_statuses = {"Occupied","Reserved"}

        stands = list(session.scalars(select(models.Stand)))
        candidates = [s for s in stands if getattr(s, "status", None) not in unavailable_statuses]

        def cat(s) -> str | None:
            return stand_category(getattr(s, "type", None))

        preferred_stands = [s for s in candidates if cat(s) == preferred]
        chosen = preferred_stands[0] if preferred_stands else None
        if chosen is None:
            o_stands = [s for s in candidates if cat(s) == "O"]
            if not o_stands:
                return None
            chosen = o_stands[0]
        
        session.execute(
            update(models.Stand)
            .where(models.Stand.id == chosen.id)
            .values(status="Reserved", airplane_id=airplane_id)
        )
        session.execute(
            update(models.Flight)
            .where(models.Flight.id == flight_id)
            .values(status="Landing")
        )
        session.execute(
            update(models.Airplane)
            .where(models.Airplane.id == airplane_id)
            .values(status="Reserved")
        )
        session.commit()
        return chosen.id
