from __future__ import annotations

import unittest

from src.domain.status_constants import LANDING_PARAMETERS
from src.utils.landing_timing import landing_spawn_lead_seconds


class LandingTimingTests(unittest.TestCase):
    def test_route_lead_uses_unity_units_and_segment_target_speeds(self) -> None:
        splines = {
            "Fast": {"name": "Fast", "lengthMeters": 10.0},
            "Slow": {"name": "Slow", "lengthMeters": 5.0},
        }

        segments = [
            {
                "name": "Fast",
                "t_start": 0.0,
                "t_end": 1.0,
                "speed_profile": {"target_speed_kmh": 36.0},
            },
            {
                "name": "Slow",
                "t_start": 0.0,
                "t_end": 1.0,
                "speed_profile": {"target_speed_kmh": 18.0},
            },
        ]

        lead_seconds = landing_spawn_lead_seconds(
            spawn_position={"x": 0.0, "y": 0.0, "z": 0.0},
            airport_position={"x": 1.0, "y": 0.0, "z": 0.0},
            route_segments=segments,
            spline_lookup=splines.get,
            final_landing_to_stand_seconds=0.0,
        )

        expected_seconds = (
            10.0 * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT / 10.0
            + 5.0 * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT / 5.0
        )

        self.assertAlmostEqual(lead_seconds, expected_seconds)

    def test_route_lead_uses_schedule_speed_and_stops_at_touchdown(self) -> None:
        splines = {
            "Inbound": {"name": "Inbound", "lengthUnits": 10.0},
            "Runway": {"name": "Runway", "lengthUnits": 2.0},
            "Taxi": {"name": "Taxi", "lengthUnits": 1000.0},
        }

        segments = [
            {
                "name": "Inbound",
                "t_start": 0.0,
                "t_end": 1.0,
                "speed_profile": {
                    "target_speed_kmh": 3.0,
                    "schedule_speed_kmh": 360.0,
                    "purpose": "landing_inbound_fast",
                },
            },
            {
                "name": "Runway",
                "t_start": 0.0,
                "t_end": 1.0,
                "speed_profile": {
                    "target_speed_kmh": 0.6,
                    "schedule_speed_kmh": 180.0,
                    "purpose": "landing_range_final",
                },
            },
            {
                "name": "Taxi",
                "t_start": 0.0,
                "t_end": 1.0,
                "speed_profile": {
                    "target_speed_kmh": 0.25,
                    "schedule_speed_kmh": 25.0,
                    "purpose": "taxi_after_landing",
                },
            },
        ]

        lead_seconds = landing_spawn_lead_seconds(
            spawn_position={"x": 0.0, "y": 0.0, "z": 0.0},
            airport_position={"x": 1.0, "y": 0.0, "z": 0.0},
            route_segments=segments,
            spline_lookup=splines.get,
            final_landing_to_stand_seconds=0.0,
        )

        expected_seconds = (
            10.0 * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT / 100.0
            + 2.0 * LANDING_PARAMETERS.METERS_PER_UNITY_UNIT / 50.0
        )

        self.assertAlmostEqual(lead_seconds, expected_seconds)


if __name__ == "__main__":
    unittest.main()
