from datetime import datetime, timedelta, timezone
import unittest

from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler


class _Flight:
    def __init__(self, flight_id: str, *, origin: str, status: str, departure_time: datetime):
        self.id = flight_id
        self.origin = origin
        self.status = status
        self.departure_time = departure_time


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


if __name__ == "__main__":
    unittest.main()
