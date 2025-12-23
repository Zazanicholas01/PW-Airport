from uuid import uuid4
from src.db import models
import random
from datetime import datetime, date, timedelta, timezone

from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete

from src.db.engine import get_engine

class RandomFlightGenerator:
    def __init__(self, session_factory):
        self.flights = []
        self.personal_airport = "LIAG"
        self.Session = session_factory or sessionmaker(bind=get_engine(), future=True)
        self._airports = []
        self._airlines = []
        self._terminals = []
    
    def load_metadata(self, session):
        airports = (
            session.query(models.Airport)
            .filter(models.Airport.icao != self.personal_airport)
            .all()
        )
        terminals = session.query(models.Terminal).all()
        airlines = (
            session.query(models.Airline)
            .filter(models.Airline.icao.in_(["LUN", "UMB", "JAE", "ALI"]))
            .all()
        )
        return airports, terminals, airlines
    

    def _random_seconds_between(self, start: datetime, end: datetime) -> int:
        if end <= start:
            raise ValueError("Invalid time window")
        return random.randint(0, int((end - start).total_seconds()))
    

    def _random_time_between(self, start: datetime, end: datetime) -> datetime:
        return start + timedelta(seconds=self._random_seconds_between(start, end))


    def _times_departure_within_window_today(
        self,
        *,
        window: timedelta,
        min_duration: timedelta = timedelta(minutes=30),
        max_duration: timedelta = timedelta(minutes=240),
        guard: timedelta = timedelta(minutes=1),
    ) -> tuple[datetime, datetime]:
        now = self._utc_now_naive()
        today = now.date()
        start_of_day = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        dep_lower = now + guard
        dep_upper = min(now + window - guard, end_of_day - min_duration)
        if dep_lower >= dep_upper:
            return self._random_times_for_today(min_departure_delta=timedelta(seconds=0))

        dep_time = self._random_time_between(dep_lower, dep_upper)

        max_allowed_seconds = int((end_of_day - dep_time).total_seconds())
        min_dur = int(min_duration.total_seconds())
        max_dur = min(int(max_duration.total_seconds()), max_allowed_seconds)

        if max_dur < min_dur:
            return self._random_times_for_today(min_departure_delta=timedelta(seconds=0))
        
        duration_seconds = random.randint(min_dur, max_dur)

        arr_time = dep_time + timedelta(seconds=duration_seconds)
        return dep_time, arr_time


    def _times_arrival_within_window_today(
        self,
        *,
        window: timedelta,
        min_duration: timedelta = timedelta(minutes=30),
        max_duration: timedelta = timedelta(minutes=240),
        guard: timedelta = timedelta(minutes=1),
    ) -> tuple[datetime, datetime]:
        now = self._utc_now_naive()
        today = now.date()
        start_of_day = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        arr_lower = max(now + guard + min_duration, start_of_day + min_duration)
        arr_upper = min(now + window - guard, end_of_day - guard)
        if arr_lower >= arr_upper:
            return self._random_times_for_today(min_departure_delta=timedelta(seconds=0))

        arr_time = self._random_time_between(arr_lower, arr_upper)

        max_back_seconds = int((arr_time - start_of_day).total_seconds())
        max_by_now_seconds = int((arr_time - (now + guard)).total_seconds())
        min_dur = int(min_duration.total_seconds())
        max_dur = min(int(max_duration.total_seconds()), max_back_seconds, max_by_now_seconds)

        if max_dur < min_dur:
            duration_seconds = min_dur
        else:
            duration_seconds = random.randint(min_dur, max_dur)

        dep_time = arr_time - timedelta(seconds=duration_seconds)
        return dep_time, arr_time


    def _random_times_for_today(
        self,
        *,
        min_departure_delta: timedelta = timedelta(hours=2),
        min_duration: timedelta = timedelta(minutes=30),
        max_duration: timedelta = timedelta(minutes=240),
    ) -> tuple[datetime, datetime]:
        now = self._utc_now_naive()
        today = now.date()

        start_of_day = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        earliest_departure = max(start_of_day, now + min_departure_delta)
        latest_departure = end_of_day - min_duration

        if earliest_departure > latest_departure:
            raise RuntimeError(
                f"Not enough time remaining today to schedule flights "
                f"(now={now.isoformat()}, min_departure_delta={min_departure_delta})."
            )

        window_seconds = int((latest_departure - earliest_departure).total_seconds())
        dep_time = earliest_departure + timedelta(seconds=random.randint(0, window_seconds))

        max_allowed_seconds = int((end_of_day - dep_time).total_seconds())
        min_duration_seconds = int(min_duration.total_seconds())
        max_duration_seconds = min(int(max_duration.total_seconds()), max_allowed_seconds)

        if max_duration_seconds < min_duration_seconds:
            raise RuntimeError("Invalid duration window for today-only flight generation.")

        duration_seconds = random.randint(min_duration_seconds, max_duration_seconds)
        arr_time = dep_time + timedelta(seconds=duration_seconds)
        return dep_time, arr_time


    def _init_flight_counters(self, session, airlines) -> dict[str, int]:

        counters = {a.icao: 0 for a in airlines}

        existing_flights = (
            session.query(models.Flight)
            .filter(
                models.Flight.airline_code.in_(counters.keys()),
                models.Flight.icao.isnot(None),
            )
            .all()
        )

        for f in existing_flights:
            code = f.icao or ""
            parts = code.split("_")

            if len(parts) < 2:
                continue

            airline_code = f.airline_code or ""
            if parts[0] != airline_code:
                continue
            num_part = parts[1]
            if len(num_part) == 4 and num_part.isdigit():
                n = int(num_part)
                if n > counters[airline_code]:
                    counters[airline_code] = n
        
        return counters


    def _next_flight_code(self, airline, counters) -> str:

        current = counters.get(airline.icao, 0) + 1
        if current > 9999:
            raise RuntimeError("Flight Number overflow")

        counters[airline.icao] = current
        return current


    def _pick_terminal_id(self, terminals: list[models.Terminal], flight_type: str) -> int:

        t_type = flight_type.lower()
        if t_type == "passengers":
            candidates = [
                t for t in terminals
                if isinstance(t.type, str) and "passeg" in t.type.lower()
            ]
        else:
            candidates = [
                t for t in terminals
                if isinstance(t.type, str)
                and ("cargo" in t.type.lower())
            ]
        
        if not candidates:
            candidates = terminals
            raise RuntimeError("No terminals available")

        return random.choice(candidates).id
    

    def _route_category(self, remote_airport: models.Airport) -> str:

        country = (remote_airport.country or "").lower()

        if country == "italia":
            return "National"
        
        european_countries = {
            "francia",
            "germania",
            "paesi bassi",
            "spagna",
            "regno unito",
            "turchia",
        }

        if country in european_countries:
            return "European"
        
        return "International"


    def _pick_airline(self, airlines: list[models.Airline], flight_type: str, route_category: str) -> models.Airline:

        def type_matches(a: models.Airline) -> bool:

            at = (a.type or "").lower()
            if flight_type == "Cargo":
                return "cargo" in at
            
            return "cargo" not in at

        allowed_nationalities = {"NI-EU"}
        if route_category == "National":
            allowed_nationalities.add("N")
        elif route_category == "European":
            allowed_nationalities.add("EU")
        elif route_category == "International":
            allowed_nationalities.add("I")
        
        candidates = [
            a for a in airlines
            if type_matches(a) and (a.nationality in allowed_nationalities)
        ]

        if not candidates:
            candidates = [a for a in airlines if type_matches(a)]
        
        if not candidates:
            candidates = list(airlines)
        
        if not candidates:
            raise RuntimeError("No airlines available")

        return random.choice(candidates)


    def _utc_now_naive(self) -> datetime:
        return datetime.now(timezone.utc)

    def generate_flights(self, n: int, *, ensure_in_window: bool = True, window: timedelta = timedelta(hours=1)) -> list[models.Flight]:

        if n <= 0:
            return []

        today = self._utc_now_naive().date()
        flights: list[models.Flight] = []

        with self.Session() as session:
            session.execute(
                delete(models.Flight)
            )
            session.commit()

            airports, terminals, airlines = self.load_metadata(session)

            if not airports:
                raise RuntimeError("No remote airports available")
            
            if not terminals:
                raise RuntimeError("No terminals available")

            if not airlines:
                raise RuntimeError("No airlines available")
            
            counters = self._init_flight_counters(session, airlines)
            
            for idx in range(n):
                if ensure_in_window and idx == 0:
                    is_departure_from_personal = True
                elif ensure_in_window and idx == 1:
                    is_departure_from_personal = False
                else:
                    is_departure_from_personal = random.choice([True, False])

                flight_type = random.choice(["Cargo", "Passengers"])
                terminal_id = self._pick_terminal_id(terminals, flight_type)

                remote_airport = random.choice(airports)

                if is_departure_from_personal:
                    origin = self.personal_airport
                    destination = remote_airport.icao
                else:
                    origin = remote_airport.icao
                    destination = self.personal_airport
                
                route_category = self._route_category(remote_airport)
                airline = self._pick_airline(airlines, flight_type, route_category)
                
                if ensure_in_window and idx == 0:
                    departure_time, arrival_time = self._times_departure_within_window_today(window=window)
                elif ensure_in_window and idx == 1:
                    departure_time, arrival_time = self._times_arrival_within_window_today(window=window)
                else:
                    departure_time, arrival_time = self._random_times_for_today(min_departure_delta=timedelta(hours=2))

                flight_number = self._next_flight_code(airline, counters)
                seq_number = 1
                date_str = today.strftime("%Y%m%d")
                full_icao = f"{airline.icao}_{flight_number:04d}_{date_str}_{origin}_{destination}_{seq_number}"

                flight = models.Flight(
                    id=str(uuid4()),
                    airplane_id=None,
                    arrival_time=arrival_time,
                    departure_time=departure_time,
                    terminal_id=terminal_id,
                    origin=origin,
                    destination=destination,
                    status="Unscheduled",
                    icao=full_icao,
                    date=today,
                    tipo=flight_type,
                    airline_code=airline.icao,
                )
                session.add(flight)
                flights.append(flight)
            
            session.commit()
        
        return flights

