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
    handled: set[tuple[str, str]] = field(default_factory=set)

    def _once(self, flight, stage: str) -> bool:
        flight_id = getattr(flight, "id", None)
        if not isinstance(flight_id, str) or not flight_id:
            return False
        
        key = (flight_id, stage)
        if key in self.handled:
            return False
        self.handled.add(key)
        return True

    def should_schedule_departure(self, *, flight, now_utc: datetime) -> bool:
        if getattr(flight, "origin", None) != self.airport_icao:
            return False
        
        if getattr(flight, "status", None) != "Unscheduled":
            return False
        
        dep_utc = as_utc(getattr(flight, "departure_time", None))
        if dep_utc is None:
            return False
        
        if (dep_utc - now_utc) > self.window:
            return False
        
        return self._once(flight, "dep")
    
    def should_assign_landing_plane(self, *, flight, now_utc: datetime) -> bool:
        if getattr(flight, "destination", None) != self.airport_icao:
            return False
        
        if getattr(flight, "status", None) != "Unscheduled":
            return False
        
        dep_utc = as_utc(getattr(flight, "departure_time", None))
        if dep_utc is None:
            return False
        
        if (dep_utc - now_utc) > self.window:
            return False
        
        return self._once(flight, "landing_dep")
    
    def should_reserve_landing_stand(self, *, flight, now_utc: datetime) -> bool:
        if getattr(flight, "destination", None) != self.airport_icao:
            return False
        
        if getattr(flight, "status", None) != "Ongoing":
            return False
        
        if getattr(flight, "airplane_id", None) is None:
            return False
        
        arr_utc = as_utc(getattr(flight, "arrival_time", None))
        if arr_utc is None:
            return False
        if (arr_utc - now_utc) > self.window:
            return False
        return self._once(flight, "landing_arr")

    def mark_scheduled(self, flight_id: str) -> None:
        self.scheduled_flight_ids.add(flight_id)
    
    def should_mark_landing_departed(self, *, flight, now_utc: datetime) -> bool:
        if getattr(flight, "destination", None) != self.airport_icao:
            return False
        if getattr(flight, "status", None) != "Scheduled":
            return False
        
        dep_utc = as_utc(getattr(flight, "departure_time", None))
        if dep_utc is None or dep_utc > now_utc:
            return False
        
        return self._once(flight, "landing_departed")
