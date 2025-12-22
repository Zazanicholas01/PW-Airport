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
    started_flight_ids: set[str] = field(default_factory=set)

    def should_start(self, *, flight, now_utc: datetime) -> bool:
        flight_id = getattr(flight, "id", None)
        if not isinstance(flight_id, str) or flight_id in self.started_flight_ids:
            return False
        
        event_utc = flight_event_time_utc(flight, airport_icao=self.airport_icao)
        if event_utc is None:
            return False
        
        if (event_utc - now_utc) <= self.window:
            self.started_flight_ids.add(flight_id)
            return True
        
        return False
