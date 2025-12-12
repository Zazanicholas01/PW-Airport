from uuid import uuid4
from src import models
import random
from datetime import datetime, date, timedelta

from sqlalchemy.orm import sessionmaker

from src.database import get_engine

class RandomFlightGenerator:
    def __init__(self, session_factory):
        self.flights = []
        self.personal_aiport = "LIAG"
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


    def pick_terminal_id(self, terminals: list[models.Terminal], flight_type: str) -> int:

        t_type = flight_type.lower()
        if t_type == "passeggeri":
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
    

    def _random_times_for_today(self) -> tuple[datetime, datetime]:
        
        today = date.today()
        start_of_day = datetime(today.year, today.month, today.day)
        dep_offset_minutes = random.randint(0, 21*60)
        dep_time = start_of_day + timedelta(minutes=dep_offset_minutes)

        duration_minutes = random.randint(30, 240)
        arr_time = dep_time + timedelta(minutes=duration_minutes)
        return dep_time, arr_time
    

    def _route_category(self, remote_airport: models.Airport) -> str:

        country = (remote_airport.country or "").lower()

        if country == "italia":
            return "Nazionale"
        
        european_countries = {
            "francia",
            "germania",
            "paesi bassi",
            "spagna",
            "regno unito",
            "turchia",
        }

        if country in european_countries:
            return "Europeo"
        
        return "Internazionale"


    def _pick_airline(self, airlines: list[models.Airline], flight_type: str, route_category: str) -> models.Airline:

        def type_matches(a: models.Airline) -> bool:

            at = (a.type or "").lower()
            if flight_type == "Merce":
                return "cargo" in at
            
            return "cargo" not in at

        allowed_nationalities = {"NI-EU"}
        if route_category == "Nazionale":
            allowed_nationalities.add("N")
        elif route_category == "Europeo":
            allowed_nationalities.add("EU")
        elif route_category == "Internazionale":
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


    def generate_flights(self, n: int) -> list[models.Flight]:

        if n <= 0:
            return []

        today = date.today()
        flights: list[models.Flight] = []

        with self.Session() as session:
            airports, terminals, airlines = self._load_metadata(session)

            if not airports:
                raise RuntimeError("No remote airports available")
            
            if not terminals:
                raise RuntimeError("No terminals available")

            if not airlines:
                raise RuntimeError("No airlines available")
            
            counters = self._init_flight_counters(session, airlines)
            
            for _ in range(n):
                is_departure_from_personal = random.choice([True, False])

                flight_type = random.choice(["Merce", "Passeggero"])
                terminal_id = self._pick_terminal_id(terminals, flight_type)

                remote_airport = random.choice(airports)

                if is_departure_from_personal:
                    origin = self.personal_aiport
                    destination = remote_airport.icao
                else:
                    origin = remote_airport.icao
                    destination = self.personal_aiport
                
                route_category = self._route_category(remote_airport)
                airline = self._pick_airline(airlines, flight_type, route_category)
                
                departure_time, arrival_time = self._random_times_for_today()

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

