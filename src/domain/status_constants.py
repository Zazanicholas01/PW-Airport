from dataclasses import dataclass
from datetime import timedelta

# Global constants
PERSONAL_AIRPORT = "LIAG"
ALLOWED_AIRLINES = ("LUN", "UMB", "JAE", "ALI")

EUROPEAN_COUNTRIES = {
    "francia",
    "germania",
    "paesi bassi",
    "spagna",
    "regno unito",
    "turchia",
}

ALLOWED_NATIONALITIES = {"NI-EU"}

MODEL_INFO: dict[str, tuple[str, str]] = {
    "turboelica": ("Passengers", "Short"),
    "jet": ("Passengers", "Short"),
    "b2_stealth": ("Passengers", "Short"),
    "aeroplanoleggendario": ("Passengers", "Short"),
    "turboelica_cargo": ("Cargo", "Short"),
    "e190": ("Passengers", "Medium"),
    "a320": ("Passengers", "Medium"),
    "b737": ("Passengers", "Medium"),
    "b737_cargo": ("Cargo", "Medium"),
    "b787": ("Passengers", "Long"),
    "beluga": ("Cargo", "Long"),
}

MODEL_CAPACITY: dict[str, int] = {
    "turboelica": 30,
    "jet": 20,
    "b2_stealth": 10,
    "aeroplanoleggendario": 12,

    "turboelica_cargo": 80,

    "e190": 100,
    "a320": 180,
    "b737": 160,

    "b737_cargo": 140,

    "b787": 280,
    "beluga": 320,
}

EXCLUDED_STAND_IDS: set[str] = {
    "LongLanding",
    "MediumLanding",
    "ShortLanding",
    "Departure",
    "Parking1",
    "Parking2",
    "Parking3",
}

AVAILABLE_STANDS = ["O1", "O2", "O3", "O4", "O5", "P1", "P2", "P3", "C1", "C2", "C3"]

PASSENGER_STANDS = ["P1", "P2", "P3"]
CARGO_STANDS = ["C1", "C2", "C3"]
OPEN_STANDS = ["O1", "O2", "O3", "O4", "O5"]

BUS_HOME_P = "BusHome_P"
BUS_HOME_O = "BusHome_O"

CARGO_HOME_P = "CargoHome_P"
CARGO_HOME_C = "CargoHome_C"
CARGO_HOME_O = "CargoHome_O"

BUS_MASTER_O_SPLINE = "Bus_Spline_Master_O"
CARGO_MASTER_O_SPLINE = "Cargo_Spline_Master_O"

DISEMBARK_SIM_SECONDS = 5 * 60
EMBARK_SIM_SECONDS = 5 * 60


@dataclass
class BUS_SERVICE_CONFIG:
    PASSENGER_TRANSFER_TIME = 30
    LUGGAGE_TRANSFER_TIME = 20
    CARGO_TRANSFER_TIME = 40

@dataclass
class GENERATOR_CONFIG:
    # Flight generation knobs
    TOTAL_N_FLIGHTS = 10
    DEPARTURE_N_FLIGHTS = 5
    ARRIVAL_N_FLIGHTS = 5

    # Time windows are deltas from "now", in minutes.
    DEPARTURE_MIN_DELTA_MINUTES = 60
    DEPARTURE_MAX_DELTA_MINUTES = 120
    ARRIVAL_MIN_DELTA_MINUTES = 30
    ARRIVAL_MAX_DELTA_MINUTES = 60

    # Backwards-compatible alias used by the scheduler loop.
    RANDOM_FLIGHTS_COUNT = TOTAL_N_FLIGHTS
    ENSURE_IN_WINDOW = True

    # Runtime generator configuration
    RUNTIME_FLIGHT_BATCH_MIN = 1
    RUNTIME_FLIGHT_BATCH_MAX = 2
    RUNTIME_FLIGHT_EVERY = timedelta(hours=1)


MIN_POLL_REAL_S = 0.05
CLOCK_HERTZ = 10.0

LOG_EVERY_S = 10.0

EVT_EVERY_S = 0.5

WINDOW_TIMEDELTA_HOURS = 1
WAIT_FOR_PARKED_TIMEOUT_S = 10

DEFAULT_PLANE_SPEED = 0.2

# File constants
NODE_SCHEMA_JSON_PATH = "schema_nodi.json"

@dataclass
class LANDING_PARAMETERS:
    LANDING_AVG_SPEED_KMH = 180.0
    METERS_PER_UNITY_UNIT = 867.08

    MIN_LANDING_SPAWN_LEAD_SECONDS = 20
    FINAL_LANDING_TO_STAND_SECONDS = 60

# Airline categories
@dataclass
class AIRLINE_CATEGORIES:
    NATIONAL = "National"
    EUROPEAN = "European"
    INTERNATIONAL = "International"

    NATIONAL_CODE = "N"
    EUROPEAN_CODE = "EU"
    INTERNATIONAL_CODE = "I"

# Flight statuses
@dataclass
class FLIGHT_STATUS:
    UNSCHEDULED = "Unscheduled"
    STAND_RESERVED = "StandReserved"
    SCHEDULED = "Scheduled"
    EMBARKING = "Embarking"
    DEPARTING = "Departing"
    DEP_ONGOING = "Dep_Ongoing"
    LAN_ONGOING = "Lan_Ongoing"
    LANDING = "Landing"
    DISEMBARKING = "Disembarking"
    COMPLETED = "Completed"
    LANDING_INBOUND = (LANDING, LAN_ONGOING, SCHEDULED, DISEMBARKING)
    DEPARTING_OUTBOUND = (EMBARKING, DEPARTING, SCHEDULED, DEP_ONGOING)
    NEEDS_AIRPLANE = (UNSCHEDULED,)

    CARGO_TYPE = "Cargo"
    PASSEGNERS_TYPE = "Passengers"
    AVAILABLE_TYPES = ("Cargo", "Passengers")


# Stand statuses
@dataclass
class STAND_STATUS:
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    OCCUPIED = "Occupied"
    UNAVAILABLE = (OCCUPIED, RESERVED)

    PASSENGERS_CATEGORY = "P"
    CARGO_CATEGORY = "C"
    O_CATEGORY = "O"
    CATEGORIES = (PASSENGERS_CATEGORY, CARGO_CATEGORY, O_CATEGORY)


# Airplane statuses
@dataclass
class AIRPLANE_STATUS:
    PARKED = "Parked"
    RESERVED = "Reserved"
    SCHEDULED = "Scheduled"
    EMBARKING = "Embarking"
    DEPARTING = "Departing"
    IN_FLIGHT = "InFlight"
    DISEMBARKING = "Disembarking"
    IN_PARKING = "InParking"
    AVAILABLE_FOR_DEPARTURE = (PARKED,)

    RANGE_SHORT = "Short"
    RANGE_MEDIUM = "Medium"
    RANGE_LONG = "Long"
    RANGES = (RANGE_SHORT, RANGE_MEDIUM, RANGE_LONG)

    CARGO_TYPE = "Cargo"
    PASSEGNERS_TYPE = "Passengers"
    AVAILABLE_TYPES = ("Cargo", "Passengers")


# Lifecycle Statuses for List in sliding window query
LIFECYCLE_STATUSES = (
    FLIGHT_STATUS.SCHEDULED,
    FLIGHT_STATUS.EMBARKING,
    FLIGHT_STATUS.DEPARTING,
    FLIGHT_STATUS.DEP_ONGOING,
    FLIGHT_STATUS.LAN_ONGOING,
    FLIGHT_STATUS.LANDING,
    FLIGHT_STATUS.DISEMBARKING,
)


# Runtime events
@dataclass
class RUNTIME_EVENTS:
    PATH_COMPLETED = "path_completed"
    PLANE_LEFT_STAND = "plane_left_stand"
    PARKING_ENTERED = "parking_entered"
    VEHICLE_ARRIVED = "vehicle_arrived"
    VEHICLE_RETURNED_HOME = "vehicle_returned_home"

# Bus commands
@dataclass
class BUS_COMMANDS:
    SPAWN_PLANE = "spawn_plane"
    SET_TIME_SCALE = "set_time_scale"
    SET_SIM_TIME = "set_sim_time"
    CLOCK_SYNC = "clock_sync"
    WELCOME = "welcome"
    START_PATH = "start_path"
    DESPAWN_PLANE = "despawn_plane"
    CONTINUE_PATH = "continue_path"
    CLEAR_PARKING = "clear_parking"
    START_VEHICLE_PATH = "start_vehicle_path"

# Websocket configuration
@dataclass
class WEBSOCKET_CONFIG:
    HOST = "0.0.0.0"
    PORT = 8765
    MAX_SIZE = 4 * 1024 * 1024
    PING_INTERVAL = 60
    PING_TIMEOUT = 60
    MAX_QUEUE = 32

# Spline related constants
DEPARTURE_SPLINE = "Departure"
SHORT_LANDING_SPLINE = "ShortLanding"
MEDIUM_LANDING_SPLINE = "MediumLanding"
LONG_LANDING_SPLINE = "LongLanding"
LANDING_SOURCES = (LONG_LANDING_SPLINE, MEDIUM_LANDING_SPLINE, SHORT_LANDING_SPLINE)
MASTER_SPLINE = "MasterSpline"

LANDING_ROUTE_SPLINE = "Landing_Route"
LANDING_APPROACH_SPLINE = "Landing_Approach"

PARKING_SPLINES = (1, 2, 3)
