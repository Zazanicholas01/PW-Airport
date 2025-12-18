from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.db.engine import get_engine
from src.db import models

from uuid import uuid4

engine = get_engine()
Session = sessionmaker(bind=engine, future=True)

def add_terminal(session) -> None:

    #### Aggiungi Terminal ####
    terminals = [
        models.Terminal(type="Passeggeri", capacity=1200),
        models.Terminal(type="Cargo", capacity=800)
    ]
    session.add_all(terminals)
    session.commit()
    print("Creati terminal di esempio")


def evaluate_distance_airports():
    # Distanze in km dall'aeroporto di simulazione (Amaro, UD)
    distances_km = {
        "LIAG": None,
        "LIML": 309.1,
        "LIMC": 344.0,
        "LIPZ": 107.5,
        "LIMJ": 393.2,
        "LIRF": 508.5,
        "LIRN": 613.9,
        "ZSPD": 8826.9,
        "OMDB": 4403.8,
        "KORD": 7482.0,
        "KJFK": 6671.6,
        "KLAX": 9851.0,
        "EGLL": 1138.7,
        "LFPG": 840.8,
        "EDDF": 529.8,
        "EHAM": 895.0,
        "LEMD": 1487.9,
        "LTFM": 1375.8
    }

    def categorize(distance_km):
        if distance_km is None:
            return None
        if distance_km < 500:
            return "Corto"
        if distance_km < 4000:
            return "Medio"
        return "Lungo"

    airports_data = [
        {"icao": "LIAG", "name": "Aeroporto Ghiaccio", "utc": "UTC+1", "country": "Italia"},
        {"icao": "LIML", "name": "Aeroporto Linate", "utc": "UTC+1", "country": "Italia"},
        {"icao": "LIMC", "name": "Aeroporto Malpensa", "utc": "UTC+1", "country": "Italia"},
        {"icao": "LIPZ", "name": "Aeroporto Marco Polo", "utc": "UTC+1", "country": "Italia"},
        {"icao": "LIMJ", "name": "Aeroporto Genova", "utc": "UTC+1", "country": "Italia"},
        {"icao": "LIRF", "name": "Aeroporto Fiumicino", "utc": "UTC+1", "country": "Italia"},
        {"icao": "LIRN", "name": "Aeroporto Napoli", "utc": "UTC+1", "country": "Italia"},
        {"icao": "ZSPD", "name": "Aeroporto Shanghai Pudong", "utc": "UTC+8", "country": "Cina"},
        {"icao": "OMDB", "name": "Aeroporto Dubai", "utc": "UTC+4", "country": "Emirati Arabi Uniti"},
        {"icao": "KORD", "name": "Aeroporto O'Hare Chicago", "utc": "UTC-6", "country": "USA"},
        {"icao": "KJFK", "name": "Aeroporto JFK New York", "utc": "UTC-5", "country": "USA"},
        {"icao": "KLAX", "name": "Aeroporto Los Angeles", "utc": "UTC-8", "country": "USA"},
        {"icao": "EGLL", "name": "Aeroporto Heathrow Londra", "utc": "UTC+0", "country": "Regno Unito"},
        {"icao": "LFPG", "name": "Aeroporto Charles de Gaulle Parigi", "utc": "UTC+1", "country": "Francia"},
        {"icao": "EDDF", "name": "Aeroporto Francoforte", "utc": "UTC+1", "country": "Germania"},
        {"icao": "EHAM", "name": "Aeroporto Schiphol Amsterdam", "utc": "UTC+1", "country": "Paesi Bassi"},
        {"icao": "LEMD", "name": "Aeroporto Barajas Madrid", "utc": "UTC+1", "country": "Spagna"},
        {"icao": "LTFM", "name": "Aeroporto Istanbul", "utc": "UTC+3", "country": "Turchia"},
    ]

    final_return_data = [
        models.Airport(
            icao=airport["icao"],
            name=airport["name"],
            distance=categorize(distances_km.get(airport["icao"])),
            utc=airport["utc"],
            country=airport["country"],
        )
        for airport in airports_data
    ]

    return final_return_data


def add_airports(session) -> None:
    #### Aggiungi Aeroporti ####
    airports = evaluate_distance_airports()
    session.add_all(airports)
    session.commit()
    print("Creati aeroporti di esempio")


def add_airlines(session) -> None:
    #### Aggiungi Compagnie Aeree ####
    airlines = [
        models.Airline(icao="LUN", name="Lunex", type="Cargo", nationality="NI-EU"),
        models.Airline(icao="UMB", name="UmbAir", type="Passenger", nationality="EU"),
        models.Airline(icao="JAE", name="Jack Emirates", type="Passenger", nationality="I"),
        models.Airline(icao="ALI", name="Nicholas in Alice", type="Passenger", nationality="N"),
        models.Airline(icao="PRI", name="Private Airlines", type="Passenger", nationality="NI-EU"), # Jet Privato
        models.Airline(icao="GOV", name="Government Airlines", type="Passenger", nationality="NI-EU") # Stealth
    ]
    session.add_all(airlines)
    session.commit()
    print("Create compagnie aeree di esempio")


def add_stands(session) -> None:
    stands = [
        models.Stand(id="O1", type="PC", status="Libero", airplane_id=None),
        models.Stand(id="O2", type="PC", status="Libero", airplane_id=None),
        models.Stand(id="O3", type="PC", status="Libero", airplane_id=None),
        models.Stand(id="O4", type="PC", status="Libero", airplane_id=None),
        models.Stand(id="O5", type="PC", status="Libero", airplane_id=None),
        models.Stand(id="C1", type="C", status="Libero", airplane_id=None),
        models.Stand(id="C2", type="C", status="Libero", airplane_id=None),
        models.Stand(id="C3", type="C", status="Libero", airplane_id=None),
        models.Stand(id="P1", type="P", status="Libero", airplane_id=None),
        models.Stand(id="P2", type="P", status="Libero", airplane_id=None),
        models.Stand(id="P3", type="P", status="Libero", airplane_id=None),
    ]
    session.add_all(stands)
    session.commit()
    print("Creati stand di esempio")


def add_parkings(session) -> None:
    parkings = [
        models.ParkingSpot(airplane_id=None, status="Libero", spline=1),
        models.ParkingSpot(airplane_id=None, status="Libero", spline=2),
        models.ParkingSpot(airplane_id=None, status="Libero", spline=3),
    ]
    session.add_all(parkings)
    session.commit()
    print("Creati parcheggi di esempio")


def add_vehicles(session) -> None:
    vehicle_specifics = [("Bus", 50), ("Bus", 50), ("Cargo", 100), ("Cargo", 100), ("Cargo", 100), ("Fuel", 5000)]
    vehicles = []
    for vehicle in vehicle_specifics:
        vehicles.append(
            models.Vehicle(
                id=uuid4().hex[:4], 
                type=vehicle[0],
                capacity=vehicle[1],
                position={"x": 0, "y": 0, "z": 0}, # Ragionamento 
                destination=None,
                status="Disponibile",
                speed=0.0,
                route_id=None,
                flight_id=None
            )
        )
    session.add_all(vehicles)
    session.commit()
    print("Creati veicoli di esempio")


def insert_seed_values() -> None:
    x = True
    with Session() as session:
        if x:
            if not session.query(models.Terminal).first(): add_terminal(session)
            add_airports(session)
            add_airlines(session)
            add_parkings(session)
            add_stands(session)
            add_vehicles(session)


def main() -> None:
    insert_seed_values()

if __name__ == "__main__":
    main()
