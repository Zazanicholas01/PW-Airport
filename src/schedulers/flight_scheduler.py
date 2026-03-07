from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.utils.datetimes import as_utc

SLIDING_WINDOW = timedelta(hours=1)
LANDING_NEAR_DELTA = timedelta(minutes=1)

@dataclass
class FlightSlidingWindowScheduler:
    airport_icao: str
    window: timedelta = SLIDING_WINDOW
    scheduled_flight_ids: set[str] = field(default_factory=set)
    handled: set[tuple[str, str]] = field(default_factory=set)

    def _once(self, flight, stage: str) -> bool:
        """Idempotency enforcing function"""

        # Get Flight ID and validates it
        flight_id = getattr(flight, "id", None)
        if not isinstance(flight_id, str) or not flight_id:
            return False
        
        # If key already exists it blocks duplicates, otherwise records it and allows execution
        key = (flight_id, stage)
        if key in self.handled:
            return False
        
        self.handled.add(key)
        return True
    

    def _is_stage_eligible(
            self,
            *,
            flight,
            now_utc: datetime,
            expected_side: str, # Origin or Destination
            expected_status: str,
            event_field: str, # Departure time or Arrival time
            max_delta: timedelta | None,
            requires_airplane: bool = False,
            must_be_started: bool = False, # True => event_time must be <= now
    ) -> bool:
        """Shared validation for most stage checks"""

        # Check direction by matching with local airport ICAO
        if getattr(flight, expected_side, None) != self.airport_icao:
            return False
        
        # Check that the status matches the expected stage
        if getattr(flight, "status", None) != expected_status:
            return False
        
        # Check to ensure an airplane is already linked to the flight
        if requires_airplane and getattr(flight, "airplane_id", None) is None:
            return False
        
        # Get event time as UTC from selected field
        event_utc = as_utc(getattr(flight, event_field, None))
        if event_utc is None:
            return False
        
        # For "already started events" event time must not be in the future
        if must_be_started and event_utc > now_utc:
            return False
        
        # Check whether the event is inside the scheduling window / delta
        if max_delta is not None and (event_utc - now_utc) > max_delta:
            return False
        
        return True
    

    def _is_landing_near_ready(self, *, flight, now_utc: datetime) -> bool:
        """Shared predicate for near arrival landing actions"""

        return self._is_stage_eligible(
            flight=flight,
            now_utc=now_utc,
            expected_side="destination",
            expected_status="Landing",
            event_field="arrival_time",
            max_delta=LANDING_NEAR_DELTA,
            requires_airplane=True,
            must_be_started=False
        )
    

    def mark_scheduled(self, flight_id: str) -> None:
        """Insert ID into Scheduled Flight IDs list"""
        self.scheduled_flight_ids.add(flight_id)


    def should_schedule_departure(self, *, flight, now_utc: datetime) -> bool:
        """Handles Unscheduled departure flights inside the scheduling window"""

        # Check direction to be a departure flight and status to be Unscheduled
        # Get departure time as UTC and check whether it's inside the scheduling window
        if not self._is_stage_eligible(
            flight=flight,
            now_utc=now_utc,
            expected_side="origin",
            expected_status="Unscheduled",
            event_field="departure_time",
            max_delta=self.window
        ):
            return False
        
        # Returns the processing of the flight with key dep
        return self._once(flight, "dep")
    

    def should_assign_landing_plane(self, *, flight, now_utc: datetime) -> bool:
        """Handles inbound arrival flights"""

        # Check direction to be a landing flight and status to be Unscheduled
        # Get departure time and check whether it's inside the scheduling window
        if not self._is_stage_eligible(
            flight=flight,
            now_utc=now_utc,
            expected_side="destination",
            expected_status="Unscheduled",
            event_field="departure_time",
            max_delta=self.window,
        ):
            return False

        return self._once(flight, "landing_dep")
    

    def should_reserve_landing_stand(self, *, flight, now_utc: datetime) -> bool:
        """Handles ongoing arrival flights to decide whether a stand should be reserved or not"""

        # Check direction to be a landing flight, status to be Lan_Ongoing and airplane to exist
        # Get arrival time as UTC and check inside window
        if not self._is_stage_eligible(
            flight=flight,
            now_utc=now_utc,
            expected_side="destination",
            expected_status="Lan_Ongoing",
            event_field="arrival_time",
            max_delta=self.window,
            requires_airplane=True,
        ):
            return False

        return self._once(flight, "landing_arr")
    

    def should_mark_landing_departed(self, *, flight, now_utc: datetime) -> bool:
        """Handles Scheduled landing flights to check whether a plane has departed from a remote airport"""

        # Check direction to be a landing flight and status to be Scheduled
        # Get departure time as UTC and validates it to be present and not in the future
        if not self._is_stage_eligible(
            flight=flight,
            now_utc=now_utc,
            expected_side="destination",
            expected_status="Scheduled",
            event_field="departure_time",
            max_delta=None,
            must_be_started=True,
        ):
            return False
        
        return self._once(flight, "landing_departed")
    

    def should_start_departure_movement(self, *, flight, now_utc: datetime) -> bool:
        """Handles outbound scheduled flights to trigger movement start of departure flights"""

        # Check direction to be a departure flight and status to be Scheduled
        # Get departure time as UTC and check if departure time has been reached now
        if not self._is_stage_eligible(
            flight=flight,
            now_utc=now_utc,
            expected_side="origin",
            expected_status="Scheduled",
            event_field="departure_time",
            max_delta=None,
            must_be_started=True,
        ):
            return False

        return self._once(flight, "dep_start")
    

    def should_spawn_landing_plane(self, *, flight, now_utc: datetime) -> bool:
        """Handles incoming landings to trigger the spawn of a landing plane"""

        # Shared near arrival landing predicate
        if not self._is_landing_near_ready(flight=flight, now_utc=now_utc):
            return False
        
        return self._once(flight, "landing_spawn")
    

    def should_start_landing_approach(self, *, flight, now_utc: datetime) -> bool:
        """Handles incoming landings to trigger the movement of the just spawned plane"""

        # Shared near arrival landing predicate
        if not self._is_landing_near_ready(flight=flight, now_utc=now_utc):
            return False
        
        return self._once(flight, "landing_start")
