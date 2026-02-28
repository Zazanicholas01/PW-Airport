from dataclasses import dataclass

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

DISEMBARK_SIM_SECONDS = 5 * 60

RANDOM_FLIGHTS_COUNT = 20
ENSURE_IN_WINDOW = True

MIN_POLL_REAL_S = 0.05
CLOCK_HERTZ = 10.0

LAST_LOG_T = 0.0
LOG_EVERY_S = 10.0

LAST_EVT_T = 0.0
EVT_EVERY_S = 0.5

# File constants
NODE_SCHEMA_JSON_PATH = "schema_nodi.json"

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
    ONGOING = "Ongoing"
    LANDING = "Landing"
    DISEMBARKING = "Disembarking"
    COMPLETED = "Completed"
    LANDING_INBOUND = {LANDING, ONGOING, SCHEDULED, DISEMBARKING}
    NEEDS_AIRPLANE = {UNSCHEDULED}

    CARGO_TYPE = "Cargo"
    PASSEGNERS_TYPE = "Passengers"
    AVAILABLE_TYPES = {"Cargo", "Passengers"}


# Stand statuses
@dataclass
class STAND_STATUS:
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    OCCUPIED = "Occupied"
    UNAVAILABLE = {OCCUPIED, RESERVED}

    PASSENGERS_CATEGORY = "P"
    CARGO_CATEGORY = "C"
    O_CATEGORY = "O"
    CATEGORIES = {PASSENGERS_CATEGORY, CARGO_CATEGORY, O_CATEGORY}


# Airplane statuses
@dataclass
class AIRPLANE_STATUS:
    PARKED = "Parked"
    RESERVED = "Reserved"
    SCHEDULED = "Scheduled"
    IN_FLIGHT = "InFlight"
    DISEMBARKING = "Disembarking"
    AVAILABLE_FOR_DEPARTURE = {PARKED}

    RANGE_SHORT = "Short"
    RANGE_MEDIUM = "Medium"
    RANGE_LONG = "Long"
    RANGES = {RANGE_SHORT, RANGE_MEDIUM, RANGE_LONG}

    CARGO_TYPE = "Cargo"
    PASSEGNERS_TYPE = "Passengers"
    AVAILABLE_TYPES = {"Cargo", "Passengers"}


# Runtime events
@dataclass
class RUNTIME_EVENTS:
    PATH_COMPLETED = "path_completed"
    PLANE_LEFT_STAND = "plane_left_stand"

# Bus commands
@dataclass
class BUS_COMMANDS:
    SPAWN_PLANE = "spawn_plane"
    SET_TIME_SCALE = "set_time_scale"
    SET_SIM_TIME = "set_sim_time"
    CLOCK_SYNC = "clock_sync"
    WELCOME = "welcome"

# Websocket configuration
@dataclass
class WEBSOCKET_CONFIG:
    HOST = "0.0.0.0"
    PORT = 8765
    MAX_SIZE = 4 * 1024 * 1024
    PING_INTERVAL = 20
    PING_TIMEOUT = 20
    MAX_QUEUE = 32

# Spline related constants
DEPARTURE_SPLINE = "Departure"
SHORT_LANDING_SPLINE = "ShortLanding"
MEDIUM_LANDING_SPLINE = "MediumLanding"
LONG_LANDING_SPLINE = "LongLanding"
LANDING_SOURCES = (SHORT_LANDING_SPLINE, MEDIUM_LANDING_SPLINE, LONG_LANDING_SPLINE)
MASTER_SPLINE = "MasterSpline"
