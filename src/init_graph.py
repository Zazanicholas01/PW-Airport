"""
init_graph.py

Purpose:
  - Build "path recipes" (ordered spline segments) that Unity can follow to move planes:
      * Landing spline -> MasterSpline slice -> Stand spline
      * Stand spline -> MasterSpline slice -> Departure spline

Inputs:
  - `schema_nodi.json` (node/link schema) defines which stand spline is reachable at each master-knot index.
  - `master_spline` payload (Unity spline export) provides knot "x" parameters used to compute normalized t-ranges.

Output:
  - `self.paths`: list of dicts {name, source, destination, segments[]} where segments are Unity spline + t ranges.
"""

import logging
import json
from pathlib import Path

from src.domain.status_constants import *
from src.utils.geo_direction import CardinalDirection

logger = logging.getLogger(__name__)

DEPARTURE_HOLD_KNOT_INDEX = 3

class InitGraph:
    def __init__(self, airport_id: str = PERSONAL_AIRPORT):

        self.master_nodes = []
        self.master_edges = []
        self.master_spline = []
        self.splines = []
        self.airport_id = airport_id
        self.master_links = {}

    # ==================================================================================================================
    #
    #  HIGH - LEVEL FLOW
    #   1) Add Master Spline --> Stores the master spline payload
    #   2) Construct Master Links --> Loads JSON schema and builds master links mapping
    #   3) Extract T Master Edges --> Converts master spline knot positions into T intermediate ranges
    #   4) Build Paths --> Combines Landing / Stand / Departure splines with Master Spline edges into full route segments
    # 
    # ==================================================================================================================

    def add_splines(self, payload) -> None:
        """Add many splines from the given payload."""
        self.splines.extend(payload)
    

    def add_spline(self, spline) -> None:
        """Add a single spline payload."""
        self.splines.append(spline)
    

    def print_splines(self) -> None:
        """Print current splines for debugging."""
        logger.info("Graph splines: %s", self.splines)
    

    def print_master_spline(self) -> None:
        logger.info("Master Spline Knots: %s", self.master_spline)
    

    def add_master_spline(self, spline) -> None:
        """Add the master spline payload."""

        # Store master spline payload from Unity and build data structures for master links and master edges
        self.master_spline = spline
        self.construct_master_links()
        self.extract_t_master_edges()

    def _find_spline_by_name(self, name: str) -> dict | None:
        for spline in self.splines:
            if spline.get("name") == name:
                return spline
        return None

    def _knot_xz_from_entry(self, entry: dict) -> tuple[float, float] | None:
        params = entry.get("parameters") or []
        if not params:
            return None

        point = params[0]

        try:
            return float(point["x"]), float(point["z"])
        except (KeyError, TypeError, ValueError):
            return None


    def _normalized_manhattan_t_for_knot(self, spline: dict, knot_index: int) -> float | None:
        knot_entries = spline.get("knotEntries") or []
        positions = []

        for entry in knot_entries:
            pos = self._knot_xz_from_entry(entry)
            if pos is not None:
                positions.append(pos)

        if knot_index < 0 or knot_index >= len(positions):
            return None

        if len(positions) < 2:
            return 0.0

        cumulative = [0.0]

        for previous, current in zip(positions, positions[1:]):
            px, pz = previous
            cx, cz = current
            cumulative.append(cumulative[-1] + abs(cx - px) + abs(cz - pz))

        total = cumulative[-1]
        if total <= 0.000001:
            return 0.0

        return cumulative[knot_index] / total


    def _departure_hold_t(self) -> float:
        departure_spline = self._find_spline_by_name(DEPARTURE_SPLINE_NAME)
        if departure_spline is None:
            return 0.1

        hold_t = self._normalized_manhattan_t_for_knot(departure_spline, knot_index=DEPARTURE_HOLD_KNOT_INDEX)
        return 0.1 if hold_t is None else hold_t

    def construct_master_links(self) -> None:
        """Construct a list of links between nodes and other splines"""

        # Locate and load the JSON schema that describes links between master knots and stand splines
        schema_path = Path(__file__).resolve().parent.parent / NODE_SCHEMA_JSON_PATH
        try:
            with schema_path.open('r', encoding='utf-8') as f:
                links_schema = json.load(f)

        except FileNotFoundError as e:
            logger.warning("Schema file not found: %s", schema_path, exc_info=True)
            return
        
        except json.JSONDecodeError as e:
            logger.warning("Error decoding JSON schema: %s", schema_path, exc_info=True)
            return
        
        # Transform schema links into Unity spline names and store them by node index.
        # Schema links: [ "O1", "P3" ] -> stored as [ "Spline_O1", "Spline_P3" ]
        for i, node in enumerate(links_schema.get('nodes', [])):
            links = node.get('links', [])
            links = [f"{SPLINE_PREFIX}{link}" for link in links]
            self.master_links[i] = links

        logger.info("Master Links Constructed: %s", self.master_links)


    def extract_t_master_edges(self) -> None:
        """Extract the t parameters for master edges from the master spline."""

        # Read knot entries from the master spline payload.
        knots = self.master_spline.get("knotEntries", [])
        if not knots or len(knots) < 2:
            return None, None
        try:
            # Extract X coordinates used to calculate master spline lengths
            x_coords = [knot.get("parameters", [])[0]["x"] for knot in knots]
        except (KeyError, IndexError, TypeError):
            return

        # Compute master spline length based on X coords
        ms_length = x_coords[-1] - x_coords[0]
        if ms_length <= 0:
            return
        
        # Calculate intermediate T values along the master spline
        t_values = [(x - x_coords[0]) / ms_length for x in x_coords]
        
        # Convert T steps into sliced edges of the master spline
        # Example --> Edge 2-3 --> T_start 0.1 / T_end 0.25
        for i, (t_start, t_end) in enumerate(zip(t_values, t_values[1:]), start=1):
            self.master_edges.append(
                {
                    "name": f"MS_{i-1}{i}",
                    "t_start": t_start,
                    "t_end": t_end
                }
            )
        
        logger.info("Master Edges: %s", self.master_edges)


    def build_paths(self) -> None:
        """Building Paths based on Master Edges, Master Links and Splines"""
        
        def find_master_edges(start_link, end_link):
            """Returns the slicing of master edges between start link and end link"""

            # Substring master spline based on start and end knot
            # Example --> Start 3 - End 6 --> Return master spline [3:6]
            if end_link == len(self.master_edges):
                return self.master_edges[start_link:]
            
            return self.master_edges[start_link:end_link]

        def master_to_stand_tail(start_link: int, end_link: int, stand_spline: str) -> list[dict]:
            """Build MasterSpline --> StandSpline tail for landing paths"""

            # Compute the master spline slice between the landing index and the stand index.
            # !!! EDGE CASE !!! - Spline C3 needs to be reversed
            if stand_spline in REVERSED_STAND_SPLINES:
                master_edges = find_master_edges(start_link=end_link, end_link=start_link)
            else:
                master_edges = find_master_edges(start_link=start_link, end_link=end_link)

            segments = []

            if master_edges:
                if start_link > end_link:
                    segments.append({
                        "name": MASTER_SPLINE,
                        "t_start": master_edges[-1]["t_end"],
                        "t_end": master_edges[0]["t_start"],
                    })
                else:
                    segments.append({
                        "name": MASTER_SPLINE,
                        "t_start": master_edges[0]["t_start"],
                        "t_end": master_edges[-1]["t_end"],
                    })

            segments.append({
                "name": stand_spline,
                "t_start": 1.0,
                "t_end": 0.0,
            })

            return segments

        def direct_landing_prefix(landing_spline: str) -> list[dict]:
            return [
                {
                    "name": LANDING_ROUTE_SPLINE_NAME,
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": LANDING_APPROACH_SPLINE_NAME,
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": landing_spline,
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
            ]

        def parking_entry_segments(parking_n: int, direction: str) -> list[dict]:
            return [
                {
                    "name": f"{LANDING_DIRECTION_SPLINE_PREFIX}{direction}",
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": LANDING_ROUTE_SPLINE_NAME,
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": f"{ENTRY_PARKING_SPLINE_PREFIX}{parking_n}",
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": f"{SPLINE_PREFIX}{PARKING_PREFIX}{parking_n}",
                    "t_start": 0.0,
                    "t_end": 1.0,
                    "auto_start_from_previous_end": True,
                    "loop_until_cleared": True,
                    "auto_exit_to_next_start": True,
                },
            ]
        
        def parking_exit_prefix(parking_n: int, landing_spline: str) -> list[dict]:
            return [
                {
                    "name": f"{EXIT_PARKING_SPLINE_PREFIX}{parking_n}",
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": landing_spline,
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
            ]


        # Retrieve stands and spline names and add Spline_ for Unity naming convention
        available_stands = [f"{SPLINE_PREFIX}{x}" for x in AVAILABLE_STANDS]
        available_landings = [f"{SPLINE_PREFIX}{x}" for x in LANDING_SOURCES]
        available_directions = [direction.value for direction in CardinalDirection]

        # Data structures for different landing routing
        landing_paths = []
        parking_entry_paths = []
        parking_exit_paths = []

        # Build all landing paths:
        # LandingSpline -> MasterSpline slice -> StandSpline (reversed)
        landing_start_link = 0

        for landing_spline in available_landings:

            landing_id = landing_spline.replace(SPLINE_PREFIX, "")

            # For each landing spline, create a path to every available stand.
            for stand_spline in available_stands:
                
                # Find which master knot index connects to this stand spline via schema links.
                end_link = None
                for n, link in self.master_links.items():
                    if stand_spline in link:
                        end_link = int(n)
                        break    
                
                if end_link is None:
                    continue
                
                stand_id = stand_spline.replace(SPLINE_PREFIX, "")

                tail = master_to_stand_tail(
                    start_link=landing_start_link,
                    end_link=end_link,
                    stand_spline=stand_spline,
                )

                # 1. Direct Directional Route
                # Landing_{direction} --> LandingRoute --> LandingApproach --> Long/Medium/Short Landing --> MasterSpline --> Stand Spline
                base_direct_segments = direct_landing_prefix(landing_spline=landing_spline) + tail

                for direction in available_directions:
                    direct_segments = [
                        {
                            "name": f"{LANDING_DIRECTION_SPLINE_PREFIX}{direction}",
                            "t_start": 0.0,
                            "t_end": 1.0,
                        },
                    ] + base_direct_segments

                    landing_paths.append({
                        "name": f"{PATH_LANDING_ROUTE_PREFIX}{direction}_{landing_id}_{stand_id}",
                        "source": f"{LANDING_ROUTE_SPLINE}_{direction}_{landing_id}",
                        "destination": stand_id,
                        "segments": direct_segments,
                    })

                # 3. Parking exit routes
                # ParkingN --> Exit_ParkingN --> Long/Medium/Short Landing --> MasterSpline --> Stand
                for parking_n in PARKING_SPLINES:
                    exit_segments = parking_exit_prefix(parking_n, landing_spline) + tail

                    parking_exit_paths.append({
                        "name": f"{PATH_PARKING_PREFIX}{parking_n}_{landing_id}_{stand_id}",
                        "source": f"{PARKING_PREFIX}{parking_n}_{landing_id}",
                        "destination": stand_id,
                        "segments": exit_segments,
                    })

            landing_start_link += 1

        # 2. Parking entry routes
        # LandingRoute --> Entry_ParkingN --> Loop ParkingN
        for parking_n in PARKING_SPLINES:
            for direction in available_directions:
                parking_entry_paths.append({
                    "name": f"{PATH_LANDING_ROUTE_PREFIX}{direction}_{PARKING_PREFIX}{parking_n}",
                    "source": f"{LANDING_ROUTE_SPLINE}_{direction}",
                    "destination": f"{PARKING_PREFIX}{parking_n}",
                    "segments": parking_entry_segments(parking_n, direction),
                })
        
        self.landing_paths = landing_paths
        self.parking_entry_paths = parking_entry_paths
        self.parking_exit_paths = parking_exit_paths

        paths = []

        # DEPARTURE PATHS BUILD LOGIC

        # StandSpline -> MasterSpline slice -> DepartureSpline --> Departure_{direction}
        for stand_spline in available_stands:

            start_link = None
            end_link = len(self.master_edges)

            # Find the master knot index that connects to this stand spline.
            for n, link in self.master_links.items():
                if stand_spline in link:
                    start_link = int(n)
                    break
                
            if start_link is None:
                continue
                    
            # Slice the master spline from the stand index to the end (towards Departure).
            master_edges = find_master_edges(start_link=start_link, end_link=end_link)

            base_segments = []

            # 1. Stand Spline
            base_segments.append({
                "name": stand_spline,
                "t_start": 0.0,
                "t_end": 1.0
            })

            # 2. Master Spline slice
            if master_edges:
                base_segments.append({
                    "name": MASTER_SPLINE,
                    "t_start": master_edges[0]["t_start"],
                    "t_end": master_edges[-1]["t_end"]
                })

            # 3. Generic departure spline, used as hold timer before departing
            departure_hold_t = self._departure_hold_t()
            
            base_segments.append({
                "name": DEPARTURE_SPLINE_NAME,
                "t_start": 0.0,
                "t_end": 1.0,
                "departure_hold_t": departure_hold_t,
            })

            stand_id = stand_spline.replace(SPLINE_PREFIX, "")

            # 4. Directional departure route
            for direction in available_directions:
                directional_segments = list(base_segments)

                directional_segments.append({
                    "name": f"{DEPARTURE_DIRECTION_SPLINE_PREFIX}{direction}",
                    "t_start": 0.0,
                    "t_end": 1.0,
                })

                departing_id = f"{DEPARTURE_DIRECTION_PREFIX}{direction}"

                paths.append({
                    "name": f"Path_{stand_id}_{departing_id}",
                    "source": stand_id,
                    "destination": departing_id,
                    "segments": directional_segments,
                })

        # Expose the final combined path list
        self.departing_paths = paths

        vehicle_paths = self.build_ground_vehicle_paths()

        self.paths = (
            self.landing_paths
            + self.parking_entry_paths
            + self.parking_exit_paths
            + self.departing_paths
            + vehicle_paths
        )


    @staticmethod
    def single_vehicle_spline(*, spline_name: str, forward: bool) -> list[dict]:

        return [{
            "name": spline_name,
            "t_start": 0.0 if forward else 1.0,
            "t_end": 1.0 if forward else 0.0,
        }]
    

    @staticmethod
    def master_plus_branch(*, master_name: str, branch_name: str, forward: bool) -> list[dict]:

        if forward:
            return [
                {"name": master_name, "t_start": 0.0, "t_end": 1.0},
                {"name": branch_name, "t_start": 0.0, "t_end": 1.0},
            ]
        
        return [
            {"name": branch_name, "t_start": 1.0, "t_end": 0.0},
            {"name": master_name, "t_start": 1.0, "t_end": 0.0},
        ]
    

    def has_spline(self, spline_name: str) -> bool:
        return any(
            isinstance(spline, dict) and spline.get("name") == spline_name
            for spline in self.splines
        )
    

    def build_ground_vehicle_paths(self) -> None:
        paths: list[dict] = []

        # Bus + Cargo routes for passengers stands (P*)
        for stand_id in PASSENGER_STANDS:
            bus_spline = f"{BUS_SPLINE_PREFIX}{stand_id}"
            cargo_spline = f"{CARGO_SPLINE_PREFIX}{stand_id}"

            if self.has_spline(bus_spline):
                paths.append({
                    "name": f"Path_{BUS_HOME_P}_{stand_id}",
                    "source": BUS_HOME_P,
                    "destination": stand_id,
                    "segments": self.single_vehicle_spline(
                        spline_name=bus_spline,
                        forward=True,
                    ),
                })
                paths.append({
                    "name": f"Path_{stand_id}_{BUS_HOME_P}",
                    "source": stand_id,
                    "destination": BUS_HOME_P,
                    "segments": self.single_vehicle_spline(
                        spline_name=bus_spline,
                        forward=False,
                    ),
                })
            else:
                logging.warning("[init_graph] missing spline %s", bus_spline)

            if self.has_spline(cargo_spline):
                paths.append({
                    "name": f"Path_{CARGO_HOME_P}_{stand_id}",
                    "source": CARGO_HOME_P,
                    "destination": stand_id,
                    "segments": self.single_vehicle_spline(
                        spline_name=cargo_spline,
                        forward=True,
                    ),
                })
                paths.append({
                    "name": f"Path_{stand_id}_{CARGO_HOME_P}",
                    "source": stand_id,
                    "destination": CARGO_HOME_P,
                    "segments": self.single_vehicle_spline(
                        spline_name=cargo_spline,
                        forward=False,
                    ),
                })
            else:
                logging.warning("[init_graph] missing spline %s", cargo_spline)

        # Cargo-only routes for cargo stands (C*)
        for stand_id in CARGO_STANDS:
            cargo_spline = f"{CARGO_SPLINE_PREFIX}{stand_id}"

            if self.has_spline(cargo_spline):
                paths.append({
                    "name": f"Path_{CARGO_HOME_C}_{stand_id}",
                    "source": CARGO_HOME_C,
                    "destination": stand_id,
                    "segments": self.single_vehicle_spline(
                        spline_name=cargo_spline,
                        forward=True,
                    ),
                })
                paths.append({
                    "name": f"Path_{stand_id}_{CARGO_HOME_C}",
                    "source": stand_id,
                    "destination": CARGO_HOME_C,
                    "segments": self.single_vehicle_spline(
                        spline_name=cargo_spline,
                        forward=False,
                    ),
                })
            else:
                logging.warning("[init_graph] missing spline %s", cargo_spline)

        has_bus_master = self.has_spline(BUS_MASTER_O_SPLINE)
        has_cargo_master = self.has_spline(CARGO_MASTER_O_SPLINE)

        if not has_bus_master:
            logging.warning("[init_graph] missing spline %s", BUS_MASTER_O_SPLINE)
        
        if not has_cargo_master:
            logging.warning("[init_graph] missing spline %s", CARGO_MASTER_O_SPLINE)

        # Bus + Cargo routes for open stands (O*)
        for stand_id in OPEN_STANDS:
            bus_branch = f"{BUS_SPLINE_PREFIX}{stand_id}"
            cargo_branch = f"{CARGO_SPLINE_PREFIX}{stand_id}"

            if has_bus_master and self.has_spline(bus_branch):
                paths.append({
                    "name": f"Path_{BUS_HOME_O}_{stand_id}",
                    "source": BUS_HOME_O,
                    "destination": stand_id,
                    "segments": self.master_plus_branch(
                        master_name=BUS_MASTER_O_SPLINE,
                        branch_name=bus_branch,
                        forward=True,
                    ),
                })
                paths.append({
                    "name": f"Path_{stand_id}_{BUS_HOME_O}",
                    "source": stand_id,
                    "destination": BUS_HOME_O,
                    "segments": self.master_plus_branch(
                        master_name=BUS_MASTER_O_SPLINE,
                        branch_name=bus_branch,
                        forward=False,
                    ),
                })
            elif has_bus_master:
                logging.warning("[init_graph] missing spline %s", bus_branch)

            if has_cargo_master and self.has_spline(cargo_branch):
                paths.append({
                    "name": f"Path_{CARGO_HOME_O}_{stand_id}",
                    "source": CARGO_HOME_O,
                    "destination": stand_id,
                    "segments": self.master_plus_branch(
                        master_name=CARGO_MASTER_O_SPLINE,
                        branch_name=cargo_branch,
                        forward=True,
                    ),
                })
                paths.append({
                    "name": f"Path_{stand_id}_{CARGO_HOME_O}",
                    "source": stand_id,
                    "destination": CARGO_HOME_O,
                    "segments": self.master_plus_branch(
                        master_name=CARGO_MASTER_O_SPLINE,
                        branch_name=cargo_branch,
                        forward=False,
                    ),
                })
            elif has_cargo_master:
                logging.warning("[init_graph] missing spline %s", cargo_branch)
        
        return paths
