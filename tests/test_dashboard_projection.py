import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.domain.status_constants import FLIGHT_STATUS
from src.web.dashboard_projection import DashboardProjectionService, _progress_payload


class StubProjectionService(DashboardProjectionService):
    def __post_init__(self) -> None:
        super().__post_init__()
        self.build_calls = 0

    def _build_snapshot(self, *, airport: str, window_minutes: int):
        self.build_calls += 1
        return {
            "clock": {
                "sim_unix_ms": self.clock.sim_unix_ms,
                "time_scale": self.clock.time_scale,
                "bridge_status": self.clock.bridge_status,
            },
            "window": {
                "airport": airport,
                "window_minutes": window_minutes,
            },
            "flights": [],
            "planes": [],
        }


class DashboardProjectionTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self) -> StubProjectionService:
        return StubProjectionService(
            session_factory=lambda: None,
            events_file=Path("tests-dashboard-events.jsonl"),
            recompute_debounce_seconds=0.01,
        )

    def test_unscheduled_progress_is_zero(self):
        now = datetime.now(timezone.utc)
        payload = _progress_payload(
            status=FLIGHT_STATUS.UNSCHEDULED,
            departure_time=now + timedelta(minutes=10),
            arrival_time=now + timedelta(hours=1),
            now=now,
        )
        self.assertEqual(payload["percent"], 0)
        self.assertEqual(payload["phase"], "scheduled")

    async def test_recompute_is_coalesced(self):
        service = self.make_service()
        service.track_view("LIAG", 60)
        service.mark_dirty({"type": "clock"})

        await service.schedule_recompute()
        await service.schedule_recompute()

        if service._recompute_task is not None:
            await service._recompute_task

        self.assertEqual(service.build_calls, 1)

    async def test_bridge_status_flows_into_snapshot(self):
        service = self.make_service()
        service.set_bridge_status("disconnected")
        snapshot = await service.get_snapshot(airport="LIAG", window_minutes=60)
        self.assertEqual(snapshot["clock"]["bridge_status"], "disconnected")

    def test_plain_logs_do_not_dirty_all_snapshots(self):
        service = self.make_service()
        service.track_view("LIAG", 60)
        _ = service._snapshot_cache[("LIAG", 60)]
        service._snapshot_cache[("LIAG", 60)].dirty = False
        service.mark_dirty({"type": "log", "message": "plain info"})
        self.assertFalse(service._snapshot_cache[("LIAG", 60)].dirty)


if __name__ == "__main__":
    unittest.main()
