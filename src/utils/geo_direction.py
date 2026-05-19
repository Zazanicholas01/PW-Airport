from dataclasses import dataclass
from enum import Enum
from math import atan2, cos, degrees, floor, radians, sin

from src.domain.status_constants import (
    DEPARTURE_DIRECTION_PREFIX,
    DEPARTURE_DIRECTION_SPLINE_PREFIX,
    LANDING_DIRECTION_SPLINE_PREFIX,
    LANDING_ROUTE_SPLINE,
    PERSONAL_AIRPORT,
)

@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float

class CardinalDirection(str, Enum):
    NORD = "Nord"
    NORDEST = "Nordest"
    EST = "Est"
    SUDEST = "Sudest"
    SUD = "Sud"
    SUDOVEST = "Sudovest"
    OVEST = "Ovest"
    NORDOVEST = "Nordovest"

AIRPORT_GEO_POINTS: dict[str, GeoPoint] = {
    # Local / fictional project airport, assumed at Amaro, Friuli-Venezia-Giulia
    PERSONAL_AIRPORT: GeoPoint(latitude=46.3730, longitude=13.0960),

    # Italy
    "LIMC": GeoPoint(latitude=45.6306, longitude=8.7281),    # Milano Malpensa
    "LIMJ": GeoPoint(latitude=44.4133, longitude=8.8375),    # Genova
    "LIML": GeoPoint(latitude=45.4451, longitude=9.2767),    # Milano Linate
    "LIPZ": GeoPoint(latitude=45.5053, longitude=12.3519),   # Venezia Marco Polo
    "LIRF": GeoPoint(latitude=41.8003, longitude=12.2389),   # Roma Fiumicino
    "LIRN": GeoPoint(latitude=40.8860, longitude=14.2908),   # Napoli

    # Europe
    "EDDF": GeoPoint(latitude=50.0379, longitude=8.5622),    # Frankfurt
    "EGLL": GeoPoint(latitude=51.4706, longitude=-0.4619),   # London Heathrow
    "EHAM": GeoPoint(latitude=52.3086, longitude=4.7639),    # Amsterdam Schiphol
    "LEMD": GeoPoint(latitude=40.4719, longitude=-3.5626),   # Madrid Barajas
    "LFPG": GeoPoint(latitude=49.0128, longitude=2.5500),    # Paris Charles de Gaulle
    "LTFM": GeoPoint(latitude=41.2753, longitude=28.7519),   # Istanbul

    # Middle East / Asia
    "OMDB": GeoPoint(latitude=25.2528, longitude=55.3644),   # Dubai
    "ZSPD": GeoPoint(latitude=31.1434, longitude=121.8050),  # Shanghai Pudong

    # USA
    "KJFK": GeoPoint(latitude=40.6398, longitude=-73.7789),  # New York JFK
    "KLAX": GeoPoint(latitude=33.9425, longitude=-118.4080), # Los Angeles
    "KORD": GeoPoint(latitude=41.9786, longitude=-87.9048),  # Chicago O'Hare
}

CARDINAL_DIRECTIONS = tuple(direction.value for direction in CardinalDirection)


def landing_route_source(direction: CardinalDirection, landing_id: str) -> str:
    return f"{LANDING_ROUTE_SPLINE}_{direction.value}_{landing_id}"


def departure_route_destination(direction: CardinalDirection) -> str:
    return f"{DEPARTURE_DIRECTION_PREFIX}{direction.value}"


def initial_bearing_degrees(origin: GeoPoint, target: GeoPoint) -> float:

    # Retrieve latitude and longitude
    lat1 = radians(origin.latitude)
    lat2 = radians(target.latitude)
    delta_lon = radians(target.longitude - origin.longitude)

    y = sin(delta_lon) * cos(lat2)
    x = (
        cos(lat1) * sin(lat2)
        - sin(lat1) * cos(lat2) * cos(delta_lon)
    )

    return (degrees(atan2(y, x)) + 360.0) % 360.0


def bearing_to_cardinal_8(bearing: float) -> CardinalDirection:

    # Compute sector based on starting angle
    sector = floor((bearing + 22.5) / 45.0) % 8

    return [
        CardinalDirection.NORD,
        CardinalDirection.NORDEST,
        CardinalDirection.EST,
        CardinalDirection.SUDEST,
        CardinalDirection.SUD,
        CardinalDirection.SUDOVEST,
        CardinalDirection.OVEST,
        CardinalDirection.NORDOVEST,
    ][sector]


def direction_from_amaro(target_airport: GeoPoint) -> CardinalDirection:
    """Return direction based on AMARO"""

    bearing = initial_bearing_degrees(geo_point_for_airport(PERSONAL_AIRPORT), target_airport)
    return bearing_to_cardinal_8(bearing)


def direction_for_airport_icao(icao: str | None) -> CardinalDirection | None:
    point = geo_point_for_airport(icao)
    if point is None:
        return None

    return direction_from_amaro(point)


def landing_spline_name(direction: CardinalDirection) -> str:
    """Return landing spline name based on direction"""

    return f"{LANDING_DIRECTION_SPLINE_PREFIX}{direction.value}"


def departure_spline_name(direction: CardinalDirection) -> str:
    """Return departure spline name based on direction"""

    return f"{DEPARTURE_DIRECTION_SPLINE_PREFIX}{direction.value}"


def geo_point_for_airport(icao: str | None) -> GeoPoint | None:
    """Return latitude and longitude of an airport from the ICAO code"""

    if not icao:
        return None

    return AIRPORT_GEO_POINTS.get(icao.upper())
