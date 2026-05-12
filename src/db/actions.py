from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
import random

from sqlalchemy import select, func
from src.db import models
from src.domain.status_constants import AIRPLANE_STATUS

from src.services.flight_generator import RandomFlightGenerator

@dataclass(frozen=True)
class DbActions:
    Session: any

    def count_parked_airplanes(self) -> int:
        with self.Session() as session:
            return (
                session.execute(
                    select(func.count())
                    .select_from(models.Airplane)
                    .where(models.Airplane.status == AIRPLANE_STATUS.PARKED)
                ).scalar_one()
            )
    

    def get_airplane_route_id(self, airplane_id: str) -> str | None:

        with self.Session() as session:
            return session.execute(
                select(models.Airplane.route_id).where(models.Airplane.id == airplane_id)
            ).scalar_one_or_none()
    

    def generate_debug_flights(self, n: int, ensure_in_window: bool, window: timedelta) -> None:
        """Generate bootstrap starting flights"""

        RandomFlightGenerator(self.Session).generate_flights(
            n,
            ensure_in_window=ensure_in_window,
            window=window,
            reset_existing=True,
            force_bootstrap_compatibility=True,
        )
    

    def generate_runtime_flights(self, min_n: int, max_n: int, window: timedelta) -> int:
        """Generate flights after bootstrap, during runtime"""

        count = random.randint(min_n, max_n)

        RandomFlightGenerator(self.Session).generate_flights(
            count,
            ensure_in_window=True,
            window=window,
            reset_existing=False,
            force_bootstrap_compatibility=False,
        )
        return count

