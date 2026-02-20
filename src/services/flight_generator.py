from uuid import uuid4
from src.db import models
import random
from datetime import datetime, date, timedelta, timezone

from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete

from src.db.engine import get_engine
from src.db.db_functions import normalize_distance

PERSONAL_AIRPORT = "LIAG"
STATUS_UNSCHEDULED = "Unscheduled"
FLIGHT_TYPES = ("Cargo", "Passengers")
ALLOWED_AIRLINES = ("LUN", "UMB", "JAE", "ALI")

class RandomFlightGenerator:
    """
    Classe per il generatore random di voli

    - flights: lista interna di voli -- NON USATA --
    - personal_airport: DEFAULT LIAG
    - airports / airlines / terminals: -- MAI USATI --
    """

    def __init__(self, session_factory, *, rng: random.Random | None = None):
        #self.flights = []
        self.personal_airport = PERSONAL_AIRPORT
        self.Session = session_factory or sessionmaker(bind=get_engine(), future=True)
        self.rng = rng or random.Random()
        # self._airports = []
        # self._airlines = []
        # self._terminals = []
    

    def load_metadata(self, session):
        """Prende la sessione DB e esegue le query"""

        # Query sugli aeroporti diversi da quello personale LIAG
        airports = (
            session.query(models.Airport)
            .filter(models.Airport.icao != self.personal_airport)
            .all()
        )

        # Query sui Terminal
        terminals = session.query(models.Terminal).all()

        # Query sulle compagnie aeree (Escluse alcune)
        airlines = (
            session.query(models.Airline)
            .filter(models.Airline.icao.in_(ALLOWED_AIRLINES))
            .all()
        )
        return airports, terminals, airlines
    

    def _random_seconds_between(self, start: datetime, end: datetime) -> int:
        """Ritorna secondi random tra 2 datetime"""

        if end <= start:
            raise ValueError("Invalid time window")
        return self.rng.randint(0, int((end - start).total_seconds()))
    

    def _random_time_between(self, start: datetime, end: datetime) -> datetime:
        """Genera datetime random"""

        return start + timedelta(seconds=self._random_seconds_between(start, end))


    def _utc_now(self) -> datetime:
        """Ritorna il momento attuale Timezone aware"""

        return datetime.now(timezone.utc)


    def _times_departure_within_window(
        self,
        *,
        window: timedelta,
        min_duration: timedelta = timedelta(minutes=30),
        max_duration: timedelta = timedelta(minutes=240),
        guard: timedelta = timedelta(minutes=1),
    ) -> tuple[datetime, datetime]:
        
        """
            window: assicura che venga generato un viaggio all'interno della scheduling window
            min / max: durata massima e minima dello scheduling
            guard: guardia di 1 minuto per non generare viaggi immediati
        """

        now = self._utc_now()

        # Calcolo dei limiti min e max partendo da adesso
        dep_lower = now + guard
        dep_upper = now + window - guard

        # Departure time random tra i 2 limiti
        if dep_upper <= dep_lower:
            dep_time = dep_lower
        else:
            dep_time = self._random_time_between(dep_lower, dep_upper)

        # Conversione in secondi e scelta random tra i 2 limiti
        min_dur_s = int(min_duration.total_seconds())
        max_dur_s = int(max_duration.total_seconds())
        duration_s = self.rng.randint(min_dur_s, max_dur_s)

        # Arrival time --> Departure time + durata random
        arr_time = dep_time + timedelta(seconds=duration_s)
        return dep_time, arr_time

    def _times_arrival_within_window(
        self,
        *,
        window: timedelta,
        min_duration: timedelta = timedelta(minutes=30),
        max_duration: timedelta = timedelta(minutes=240),
        guard: timedelta = timedelta(minutes=1),
    ) -> tuple[datetime, datetime]:
        now = self._utc_now()

        # Calcolo dei limiti min e max
        arr_lower = now + guard + min_duration
        arr_upper = now + window - guard

        # Scelta random del tempo tra i 2 limiti
        if arr_upper <= arr_lower:
            arr_time = arr_lower
        else:
            arr_time = self._random_time_between(arr_lower, arr_upper)

        # LOGICA INCOMPRENSIBILE
        max_dur_by_lower = arr_time - (now + guard)
        effective_max = min(max_duration, max_dur_by_lower)

        # Cap a durata minima in caso inferiore e scelta random dei secondi
        if effective_max < min_duration:
            duration = min_duration
        else:
            duration_s = self.rng.randint(
                int(min_duration.total_seconds()),
                int(effective_max.total_seconds()),
            )
            duration = timedelta(seconds=duration_s)

        # Departure time --> Arrival time - random duration
        dep_time = arr_time - duration
        return dep_time, arr_time


    def _init_flight_counters(self, session, airlines) -> dict[str, int]:

        # Crea dizionario per tracciare Sequence Number
        counters = {a.icao: 0 for a in airlines}

        # Query in DB per voli esistenti
        # Filtrato per airline code e icao esistente
        existing_flights = (
            session.query(models.Flight)
            .filter(
                models.Flight.airline_code.in_(counters.keys()),
                models.Flight.icao.isnot(None),
            )
            .all()
        )

        for f in existing_flights:

            # Get ICAO code of flight and split
            code = f.icao or ""
            parts = code.split("_")

            # Controlli coerenza codice ICAO del viaggio
            if len(parts) < 2:
                continue

            airline_code = f.airline_code or ""
            if parts[0] != airline_code:
                continue

            # Parts[1] in caso di ICAO coerente corrisponde al Sequence Number
            num_part = parts[1]
            if len(num_part) == 4 and num_part.isdigit():
                n = int(num_part)
                if n > counters[airline_code]:
                    counters[airline_code] = n
        
        return counters


    def _next_flight_code(self, airline, counters) -> int:
        """Calcolo prossimo Sequence Number"""

        # Incrementa di 1 il counter fino a 9999 (Overflow)
        current = counters.get(airline.icao, 0) + 1
        if current > 9999:
            raise RuntimeError("Flight Number overflow")

        # Aggiorna contatore e ritorna
        counters[airline.icao] = current
        return current


    def _pick_terminal_id(self, terminals: list[models.Terminal], flight_type: str) -> int:
        """Sceglie terminal compatibile con il volo"""

        # Normalizzazione e controllo coerenza del tipo di volo (Cargo / Passengers)
        t_type = flight_type.lower()
        if not terminals:
            raise RuntimeError("No terminals available")

        # Build lista di candidati in base al tipo
        if t_type == "passengers":
            candidates = [
                t for t in terminals
                if isinstance(t.type, str)
                and ("passeng" in t.type.lower())
            ]
        else:
            candidates = [
                t for t in terminals
                if isinstance(t.type, str)
                and ("cargo" in t.type.lower())
            ]
        
        # FALLBACK tutti i terminal
        if not candidates:
            candidates = terminals

        # Ritorna ID terminal random tra i possibili candidati
        return self.rng.choice(candidates).id
    

    def _route_category(self, remote_airport: models.Airport) -> str:
        """Classifica rotta dal paese dell'aeroporto remoto"""

        # Recupera paese dell'aeroporto e normalizza
        # Italia --> National
        # All'interno di set Europeo --> European
        # Else --> International

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
        """Seleziona una compagnia aerea"""

        def type_matches(a: models.Airline) -> bool:
            """Check sul tipo di viaggio Cargo / Passengers"""

            at = (a.type or "").lower()
            if flight_type == "Cargo":
                return "cargo" in at
            
            return "cargo" not in at

        # N --> National
        # EU --> European
        # I --> International
        # NI-EU --> Everywhere

        allowed_nationalities = {"NI-EU"}
        if route_category == "National":
            allowed_nationalities.add("N")
        elif route_category == "European":
            allowed_nationalities.add("EU")
        elif route_category == "International":
            allowed_nationalities.add("I")
        
        # Costruisce lista di candidati per compagnie aeree
        candidates = [
            a for a in airlines
            if type_matches(a) and (a.nationality in allowed_nationalities)
        ]

        # FALLBACK --> Match solo tipo
        if not candidates:
            candidates = [a for a in airlines if type_matches(a)]
        
        # FALLBACK --> Tutte
        if not candidates:
            candidates = list(airlines)
        
        if not candidates:
            raise RuntimeError("No airlines available")

        return self.rng.choice(candidates)


# 4) parked_pairs: scegli solo coppie davvero “viabili” (range con aeroporti disponibili)

    def _maybe_force_compatible_first_departure(
        self,
        *,
        idx: int,
        ensure_in_window: bool,
        is_departure_from_personal: bool,
        airports: list[models.Airport],
        parked_pairs: list[tuple[str, str]],
        remote_airport: models.Airport,
        flight_type: str,
    ) -> tuple[models.Airport, str]:
        
        if not (ensure_in_window and idx == 0 and is_departure_from_personal and parked_pairs):
            return remote_airport, flight_type

        def airports_for_range(rng: str) -> list[models.Airport]:
            return [
                a for a in airports
                if normalize_distance(getattr(a, "distance", None)) == rng
            ]

        viable: list[tuple[str, str, list[models.Airport]]] = [
            (t, r, airports_for_range(r))
            for (t, r) in parked_pairs
            if airports_for_range(r)
        ]

        if not viable:
            return remote_airport, flight_type

        chosen_type, chosen_range, matching_airports = self.rng.choice(viable)
        return self.rng.choice(matching_airports), chosen_type



    def _build_flight(
        self,
        *,
        idx: int,
        airports: list[models.Airport],
        terminals: list[models.Terminal],
        airlines: list[models.Airline],
        parked_pairs: list[tuple[str, str]],
        counters: dict[str, int],
        ensure_in_window: bool,
        window: timedelta
    ) -> models.Flight:
        
        # Forza il primo ad essere un decollo e il secondo un atterraggio
        # Forza entrambi dentro la window per DEBUG
        is_departure_from_personal = (
            True if (ensure_in_window and idx == 0)
            else False if (ensure_in_window and idx == 1)
            else self.rng.choice([True, False])
        )

        # Random tipo e aeroporto remoto
        flight_type = self.rng.choice(FLIGHT_TYPES)
        remote_airport = self.rng.choice(airports)

        # DEBUG - Forza decollo compatibile con aerei spawnati
        remote_airport, flight_type = self._maybe_force_compatible_first_departure(
            idx=idx,
            ensure_in_window=ensure_in_window,
            is_departure_from_personal=is_departure_from_personal,
            airports=airports,
            parked_pairs=parked_pairs,
            remote_airport=remote_airport,
            flight_type=flight_type,
        )

        # Get ID Terminal compatibile con tipo di volo
        terminal_id = self._pick_terminal_id(terminals, flight_type)

        # Set source / dest in base alla direzione del volo
        if is_departure_from_personal:
            origin, destination = PERSONAL_AIRPORT, remote_airport.icao
        else:
            origin, destination = remote_airport.icao, PERSONAL_AIRPORT

        # Get compagnia aerea in base a categoria e tipo di volo
        route_category = self._route_category(remote_airport)
        airline = self._pick_airline(airlines, flight_type, route_category)

        # DEBUG - Primo decollo sempre a 1 minuto da adesso
        if ensure_in_window and idx == 0:
            departure_time = self._utc_now() + timedelta(minutes=1)
            arrival_time = departure_time + timedelta(seconds=self.rng.randint(30*60, 240*60))
        elif ensure_in_window and idx == 1:
            departure_time, arrival_time = self._times_arrival_within_window(window=window)
        else:
            departure_time, arrival_time = self._times_departure_within_window(window=window)

        # Metadati di volo (Date / ICAO Code / Flight Number)
        flight_number = self._next_flight_code(airline, counters)
        flight_date = departure_time.astimezone(timezone.utc).date()
        date_str = flight_date.strftime("%Y%m%d")
        full_icao = f"{airline.icao}_{flight_number:04d}_{date_str}_{origin}_{destination}_1"

        # Crea record finale di volo
        return models.Flight(
            id=str(uuid4()),
            airplane_id=None,
            arrival_time=arrival_time,
            departure_time=departure_time,
            terminal_id=terminal_id,
            origin=origin,
            destination=destination,
            status=STATUS_UNSCHEDULED,
            icao=full_icao,
            date=flight_date,
            tipo=flight_type,
            airline_code=airline.icao,
        )

    def generate_flights(self, n: int, *, ensure_in_window: bool = True, window: timedelta = timedelta(hours=1)) -> list[models.Flight]:
        """Generazione effettiva dei viaggi random"""

        # Sanity check su viaggi richiesti negativi o uguali a 0
        if n <= 0:
            return []

        # Inizializza lista di voli
        flights: list[models.Flight] = []

        with self.Session() as session:

            # TRUNCATE tabella voli prima di popolare di nuovo
            session.execute(
                delete(models.Flight)
            )
            session.commit()

            # Query DB per aeroporti / airlines e terminal
            airports, terminals, airlines = self.load_metadata(session)

            # Query DB su tipo e range degli aerei parcheggiati
            # Crea una lista di (tipo, range)
            parked_pairs = list(
                {
                    (t, r)
                    for (t, r) in session.query(models.Airplane.type, models.Airplane.range)
                    .filter(models.Airplane.status == "Parked")
                    .all()
                    if isinstance(t, str) and isinstance(r, str)
                }
            )

            # Sanity check
            if not airports:
                raise RuntimeError("No remote airports available")
            
            if not terminals:
                raise RuntimeError("No terminals available")

            if not airlines:
                raise RuntimeError("No airlines available")
            
            # Inizializza Sequence Numbers
            counters = self._init_flight_counters(session, airlines)
            
            # Genera n flights (Parametro input)
            for idx in range(n):

                flight = self._build_flight(
                    idx=idx,
                    airports=airports,
                    terminals=terminals,
                    airlines=airlines,
                    parked_pairs=parked_pairs,
                    counters=counters,
                    ensure_in_window=ensure_in_window,
                    window=window
                )
                session.add(flight)
                flights.append(flight)
            
            session.commit()
        
        return flights
