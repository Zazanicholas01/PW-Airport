from datetime import datetime, timedelta, timezone
import unittest

from src.domain.status_constants import FLIGHT_STATUS
from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler


class _Flight:
    def __init__(
            self,
            flight_id: str,
            *,
            origin: str,
            status: str,
            departure_time: datetime,
            destination: str | None = None,
            arrival_time: datetime | None = None,
            airplane_id: str | None = None,
    ):
        self.id = flight_id
        self.origin = origin
        self.destination = destination
        self.status = status
        self.departure_time = departure_time
        self.arrival_time = arrival_time
        self.airplane_id = airplane_id


class FlightSlidingWindowSchedulerTests(unittest.TestCase):
    def test_departure_retry_cooldown_blocks_immediate_reprocessing(self) -> None:
        scheduler = FlightSlidingWindowScheduler(airport_icao="LIML")
        now = datetime.now(timezone.utc)
        flight = _Flight(
            "F1",
            origin="LIML",
            status="Unscheduled",
            departure_time=now + timedelta(minutes=15),
        )

        self.assertTrue(scheduler.should_schedule_departure(flight=flight, now_utc=now))

        scheduler.defer_retry(flight_id="F1", stage="dep", delay_seconds=60.0)

        self.assertFalse(scheduler.should_schedule_departure(flight=flight, now_utc=now))

    def test_departure_retry_cooldown_allows_later_reprocessing(self) -> None:
        scheduler = FlightSlidingWindowScheduler(airport_icao="LIML")
        now = datetime.now(timezone.utc)
        flight = _Flight(
            "F2",
            origin="LIML",
            status="Unscheduled",
            departure_time=now + timedelta(minutes=15),
        )

        self.assertTrue(scheduler.should_schedule_departure(flight=flight, now_utc=now))

        scheduler.defer_retry(flight_id="F2", stage="dep", delay_seconds=0.0)

        self.assertTrue(scheduler.should_schedule_departure(flight=flight, now_utc=now))

    def test_dynamic_landing_departed_uses_arrival_minus_route_duration(self) -> None:
        scheduler = FlightSlidingWindowScheduler(airport_icao="LIML")
        spawn_at = datetime.now(timezone.utc)
        route_total_seconds = 40 * 60
        flight = _Flight(
            "F3",
            origin="EGLL",
            destination="LIML",
            status=FLIGHT_STATUS.SCHEDULED,
            departure_time=spawn_at - timedelta(minutes=10),
            arrival_time=spawn_at + timedelta(seconds=route_total_seconds),
            airplane_id="A1",
        )

        self.assertFalse(
            scheduler.should_mark_landing_departed_dynamic(
                flight=flight,
                now_utc=spawn_at - timedelta(seconds=1),
                lead_seconds=route_total_seconds,
            )
        )

        self.assertTrue(
            scheduler.should_mark_landing_departed_dynamic(
                flight=flight,
                now_utc=spawn_at,
                lead_seconds=route_total_seconds,
            )
        )


if __name__ == "__main__":
    unittest.main()
