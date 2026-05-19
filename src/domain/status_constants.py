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
class MESSAGE_TYPES:
    EVENT = "event"
    BACKEND_EVENT = "backend_event"


@dataclass
class BACKEND_EVENTS:
    DISEMBARK_COMPLETE = "disembark_complete"
    PARKING_ENTERED = "parking_entered"
    DEPARTURE_COMPLETED = "departure_completed"
    LANDING_COMPLETED = "landing_completed"
    PARKING_CLEARED = "parking_cleared"
    DEBUG_FLIGHTS_GENERATED = "debug_flights_generated"
    RUNTIME_FLIGHTS_GENERATED = "runtime_flights_generated"
    DEPARTURE_ASSIGNED = "departure_assigned"
    LANDING_PLANE_ASSIGNED = "landing_plane_assigned"
    LANDING_DEPARTED = "landing_departed"
    LANDING_STAND_RESERVED = "landing_stand_reserved"
    LANDING_PARKING_RESERVED = "landing_parking_reserved"
    LANDING_ARRIVAL_DELAYED = "landing_arrival_delayed"
    DEPARTURE_EMBARKING_STARTED = "departure_embarking_started"
    DEPARTURE_STARTED = "departure_started"
    LANDING_SPAWN = "landing_spawn"
    LANDING_APPROACH_STARTED = "landing_approach_started"
    INITIAL_SPAWNS_SCHEDULED = "initial_spawns_scheduled"


@dataclass
class SPAWN_CONTEXT:
    BOOTSTRAP = "bootstrap"
    LANDING = "landing"


@dataclass
class GROUND_SERVICE_TYPE:
    PASSENGER_TRANSFER = "passenger_transfer"
    LUGGAGE_TRANSFER = "luggage_transfer"
    CARGO_TRANSFER = "cargo_transfer"
    ALL = (PASSENGER_TRANSFER, LUGGAGE_TRANSFER, CARGO_TRANSFER)


@dataclass
class VEHICLE_TYPE:
    BUS = "Bus"
    CARGO = "Cargo"


@dataclass
class VEHICLE_STATUS:
    AVAILABLE = "Available"
    EN_ROUTE = "EnRoute"
    RETURNING = "Returning"
    SERVICING = "Servicing"


@dataclass
class GROUND_JOB_DIRECTION:
    TO_STAND = "to_stand"
    TO_HOME = "to_home"
    SERVICING = "servicing"


@dataclass
class GROUND_FLOW_MODE:
    LOAD = "load"
    UNLOAD = "unload"


@dataclass
class LANDING_ROUTE_DECISION:
    LAND = "land"
    PARKING = "parking"
    DELAYED = "delayed"


@dataclass
class ROUTE_KIND:
    DEPARTURE = "departure"
    LANDING = "landing"
    PARKING = "parking"
    TAXI = "taxi"


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
    START_SERVICE_PROGRESS = "start_service_progress"
    STOP_SERVICE_PROGRESS = "stop_service_progress"
    LEGACY_SPAWN = "spawn"


@dataclass
class DASHBOARD_COMMANDS:
    HIGHLIGHT_FLIGHT = "highlight_flight"

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
SPLINE_PREFIX = "Spline_"
PATH_PREFIX = "Path_"
PARKING_PREFIX = "Parking"

DEPARTURE_DIRECTION_PREFIX = "Departure_"
LANDING_DIRECTION_SPLINE_PREFIX = "Spline_Landing_"
DEPARTURE_DIRECTION_SPLINE_PREFIX = "Spline_Departure_"
BUS_SPLINE_PREFIX = "Bus_Spline_"
CARGO_SPLINE_PREFIX = "Cargo_Spline_"
ENTRY_PARKING_SPLINE_PREFIX = "Spline_Entry_Parking"
EXIT_PARKING_SPLINE_PREFIX = "Spline_Exit_Parking"
PATH_LANDING_ROUTE_PREFIX = "Path_LandingRoute_"
PATH_PARKING_PREFIX = "Path_Parking"

DEPARTURE_SPLINE = "Departure"
SHORT_LANDING_SPLINE = "ShortLanding"
MEDIUM_LANDING_SPLINE = "MediumLanding"
LONG_LANDING_SPLINE = "LongLanding"
LANDING_SOURCES = (LONG_LANDING_SPLINE, MEDIUM_LANDING_SPLINE, SHORT_LANDING_SPLINE)
MASTER_SPLINE = "MasterSpline"

LANDING_ROUTE_SPLINE = "Landing_Route"
LANDING_APPROACH_SPLINE = "Landing_Approach"

DEPARTURE_SPLINE_NAME = f"{SPLINE_PREFIX}{DEPARTURE_SPLINE}"
LANDING_ROUTE_SPLINE_NAME = f"{SPLINE_PREFIX}{LANDING_ROUTE_SPLINE}"
LANDING_APPROACH_SPLINE_NAME = f"{SPLINE_PREFIX}{LANDING_APPROACH_SPLINE}"

PARKING_SPLINES = (1, 2, 3)
REVERSED_STAND_SPLINES = {f"{SPLINE_PREFIX}C3"}
