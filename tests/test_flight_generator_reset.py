from __future__ import annotations

import random
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.db.engine import Base
from src.db import models
from src.services.flight_generator import RandomFlightGenerator


class FlightGeneratorResetTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, future=True)
        self._seed_reference_data()

    def _seed_reference_data(self) -> None:
        with self.Session() as session:
            session.add_all(
                [
                    models.Airport(icao="LIAG", name="Amaro", distance="Short", utc="UTC+1", country="Italia"),
                    models.Airport(icao="LIML", name="Milano Linate", distance="Short", utc="UTC+1", country="Italia"),
                    models.Airport(icao="LFPG", name="Paris Charles de Gaulle", distance="Medium", utc="UTC+1", country="Francia"),
                ]
            )
            session.add_all(
                [
                    models.Terminal(type="Passengers", capacity=100),
                    models.Terminal(type="Cargo", capacity=100),
                ]
            )
            session.add_all(
                [
                    models.Airline(icao="LUN", name="Luna Air", type="Passengers", nationality="NI-EU"),
                    models.Airline(icao="ALI", name="Alp Cargo", type="Cargo", nationality="NI-EU"),
                ]
            )
            session.add(
                models.Flight(
                    id="old-flight",
                    airplane_id=None,
                    arrival_time=datetime.now(timezone.utc),
                    departure_time=datetime.now(timezone.utc),
                    terminal_id=1,
                    origin="LIAG",
                    destination="LIML",
                    status="Completed",
                    icao="OLD_0001_20260512_LIAG_LIML_1",
                    date=date(2026, 5, 12),
                    tipo="Passengers",
                    airline_code="LUN",
                )
            )
            session.commit()

    def test_generate_flights_replaces_existing_flights(self) -> None:
        generator = RandomFlightGenerator(self.Session, rng=random.Random(1234))

        generator.generate_flights(2, ensure_in_window=True)

        with self.Session() as session:
            count = session.execute(select(func.count()).select_from(models.Flight)).scalar_one()
            flight_ids = set(session.scalars(select(models.Flight.id)).all())

        self.assertEqual(count, 10)
        self.assertNotIn("old-flight", flight_ids)


if __name__ == "__main__":
    unittest.main()
