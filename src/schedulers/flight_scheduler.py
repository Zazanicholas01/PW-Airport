from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

SLIDING_WINDOW = timedelta(hours=1)

def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def flight_event_time_utc(flight, *, airport_icao: str) -> datetime | None:
    if getattr(flight, "origin", None) == airport_icao:
        return as_utc(getattr(flight, "departure_time", None))
    if getattr(flight, "destination", None) == airport_icao:
        return as_utc(getattr(flight, "arrival_time", None))
    return None


@dataclass
class FlightSlidingWindowScheduler:
    airport_icao: str
    window: timedelta = SLIDING_WINDOW
    scheduled_flight_ids: set[str] = field(default_factory=set)

    def to_schedule(self, *, flight, now_utc: datetime) -> bool:
        flight_id = getattr(flight, "id", None)
        if not isinstance(flight_id, str) or flight_id in self.scheduled_flight_ids:
            return False
        
        # DEPARTURE within window from departure time
        if getattr(flight, "origin", None) == self.airport_icao:
            dep_utc = as_utc(getattr(flight, "departure_time", None))
            if dep_utc is None:
                return False
            return (dep_utc - now_utc) <= self.window
        
        # ARRIVAL only if already departed AND within window from arrival_time
        if getattr(flight, "destination", None) == self.airport_icao:
            dep_utc = as_utc(getattr(flight, "departure_time", None))
            if dep_utc is None or dep_utc > now_utc:
                return False # Not departed yet
            
            arr_utc = as_utc(getattr(flight, "arrival_time", None))
            if arr_utc is None:
                return False
            
            return (arr_utc - now_utc) <= self.window
        
        return False

    def mark_scheduled(self, flight_id: str) -> None:
        self.scheduled_flight_ids.add(flight_id)
