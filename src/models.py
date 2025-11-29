from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import relationship

from .database import Base


class Airport(Base):
    __tablename__ = "Aeroporto"

    icao = Column("ICAO", String, primary_key=True)
    name = Column("Nome", String, nullable=False)
    distance = Column("Distanza", String)
    utc = Column("UTC", String, nullable=False)
    country = Column("Paese", String, nullable=False)

    departures = relationship(
        "Flight",
        back_populates="origin_airport",
        foreign_keys="Flight.origin",
    )
    arrivals = relationship(
        "Flight",
        back_populates="destination_airport",
        foreign_keys="Flight.destination",
    )


class Airline(Base):
    __tablename__ = "Compagnia_Aerea"

    icao = Column("ICAO", String, primary_key=True)
    name = Column("Nome", String, nullable=False)
    type = Column("Tipo", String, nullable=False) # Cargo / Passeggeri
    nationality = Column("Nazionalità", String, nullable=True) # Nazionale / Europeo / Intercontinentale

    airplanes = relationship("Airplane", back_populates="airline")


class Percorso(Base):
    __tablename__ = "Percorso"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    source = Column("Sorgente", String, nullable=False)
    destination = Column("Destinazione", String, nullable=False)
    spline = Column("Spline", Integer, nullable=False)

    airplanes = relationship("Airplane", back_populates="route")
    vehicles = relationship("Vehicle", back_populates="route")


class Airplane(Base):
    __tablename__ = "Aereo"

    id = Column("Id", String, primary_key=True)
    type = Column("Tipo", String, nullable=False)
    range = Column("Raggio", String, nullable=False)
    model = Column("Modello", String, nullable=False)
    capacity = Column("Capacita", Integer, nullable=False)
    status = Column("Stato", String, nullable=False)
    speed = Column("Velocita", Float, nullable=False)
    fuel_level = Column("Livello_Carburante", Float, nullable=False)
    maintenance = Column("Manutenzione", Boolean, nullable=False)
    airline_code = Column("CA", String, ForeignKey("Compagnia_Aerea.ICAO"))
    route_id = Column("id_percorso", Integer, ForeignKey("Percorso.id"), nullable=False)

    airline = relationship("Airline", back_populates="airplanes")
    route = relationship("Percorso", back_populates="airplanes")
    flights = relationship("Flight", back_populates="airplane")
    stands = relationship("Stand", back_populates="airplane")
    operations = relationship("Operation", back_populates="airplane")
    parking_spots = relationship("ParkingSpot", back_populates="airplane")


class Terminal(Base):
    __tablename__ = "Terminal"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    type = Column("Tipo", String, nullable=False)
    capacity = Column("Capacita", Integer, nullable=False)

    flights = relationship("Flight", back_populates="terminal")


class Stand(Base):
    __tablename__ = "Piazzola"

    id = Column("id", String, primary_key=True)
    type = Column("Tipo", String, nullable=False)
    status = Column("Stato", String, nullable=False)
    airplane_id = Column("id_aereo", String, ForeignKey("Aereo.Id"))

    airplane = relationship("Airplane", back_populates="stands")
    flights = relationship("Flight", back_populates="stand")
    operations = relationship("Operation", back_populates="stand")


class Flight(Base):
    __tablename__ = "Viaggio"

    id = Column("id", String, primary_key=True)
    airplane_id = Column("id_aereo", String, ForeignKey("Aereo.Id"), nullable=False)
    arrival_time = Column("Orario_arrivo", DateTime, nullable=False)
    departure_time = Column("Orario_partenza", DateTime, nullable=False)
    terminal_id = Column("id_terminal", Integer, ForeignKey("Terminal.id"), nullable=False)
    stand_id = Column("id_piazzola", String, ForeignKey("Piazzola.id"))
    origin = Column("Provenienza", String, ForeignKey("Aeroporto.ICAO"), nullable=False)
    destination = Column("Destinazione", String, ForeignKey("Aeroporto.ICAO"), nullable=False)
    status = Column("Stato", String, nullable=False)
    icao = Column("ICAO", String, nullable=False)
    date = Column("Data", Date, nullable=False)

    airplane = relationship("Airplane", back_populates="flights")
    terminal = relationship("Terminal", back_populates="flights")
    stand = relationship("Stand", back_populates="flights")
    origin_airport = relationship(
        "Airport",
        back_populates="departures",
        foreign_keys=[origin],
    )
    destination_airport = relationship(
        "Airport",
        back_populates="arrivals",
        foreign_keys=[destination],
    )
    passengers = relationship("Passenger", back_populates="flight")
    cargo = relationship("Cargo", back_populates="flight")
    vehicles = relationship("Vehicle", back_populates="flight")
    operations = relationship("Operation", back_populates="flight")


class Vehicle(Base):
    __tablename__ = "Veicolo"

    id = Column("id", String, primary_key=True)
    type = Column("Tipo", String, nullable=False)
    capacity = Column("Capacita", Integer, nullable=False)
    position = Column("Posizione", JSON, nullable=False)
    destination = Column("Destinazione", String, nullable=False)
    status = Column("Stato", String, nullable=False)
    speed = Column("Velocita", Float, nullable=False)
    route_id = Column("id_percorso", Integer, ForeignKey("Percorso.id"), nullable=False)
    flight_id = Column("id_viaggio", String, ForeignKey("Viaggio.id"), nullable=False)

    route = relationship("Percorso", back_populates="vehicles")
    flight = relationship("Flight", back_populates="vehicles")


class Operation(Base):
    __tablename__ = "Operazione"

    id = Column("id", String, primary_key=True)
    operation_type = Column("TIpo", String, nullable=False)
    flight_id = Column("id_viaggio", String, ForeignKey("Viaggio.id"), nullable=False)
    airplane_id = Column("id_aereo", String, ForeignKey("Aereo.Id"), nullable=False)
    stand_id = Column("id_piazzola", String, ForeignKey("Piazzola.id"), nullable=False)
    status = Column("Stato", String, nullable=False)

    flight = relationship("Flight", back_populates="operations")
    airplane = relationship("Airplane", back_populates="operations")
    stand = relationship("Stand", back_populates="operations")


class Passenger(Base):
    __tablename__ = "Passeggero"

    id = Column("id", String, primary_key=True)
    first_name = Column("Nome", String, nullable=False)
    last_name = Column("Cognome", String, nullable=False)
    gender = Column("Sesso", String, nullable=False)
    age = Column("Eta", Integer, nullable=False)
    flight_id = Column("id_viaggio", String, ForeignKey("Viaggio.id"), nullable=False)
    baggage_id = Column("id_bagaglio", String, ForeignKey("Merce.id"), nullable=False)

    flight = relationship("Flight", back_populates="passengers")
    baggage = relationship(
        "Cargo",
        back_populates="passengers",
        foreign_keys=[baggage_id],
    )


class Cargo(Base):
    __tablename__ = "Merce"

    id = Column("id", String, primary_key=True)
    flight_id = Column("id_viaggio", String, ForeignKey("Viaggio.id"), nullable=False)
    terminal_id = Column("id_terminal", Integer, ForeignKey("Terminal.id"), nullable=False)
    type = Column("Tipo", String, nullable=False)
    quantity = Column("Quantita", Integer, nullable=False)
    weight = Column("Peso", Float, nullable=False)

    flight = relationship("Flight", back_populates="cargo")
    passengers = relationship("Passenger", back_populates="baggage")
    terminal = relationship("Terminal")


class ParkingSpot(Base):
    __tablename__ = "Parcheggio"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    airplane_id = Column("id_aereo", String, ForeignKey("Aereo.Id"))
    status = Column("Stato", String, nullable=False)
    spline = Column("Spline", Integer, nullable=False)

    airplane = relationship("Airplane", back_populates="parking_spots")
