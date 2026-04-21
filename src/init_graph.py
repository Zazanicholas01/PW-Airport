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
        departure_spline = self._find_spline_by_name("Spline_Departure")
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
            links = [f"Spline_{link}" for link in links]
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

        # Retrieve stands and spline names and add Spline_ for Unity naming convention
        available_stands = [f"Spline_{x}" for x in AVAILABLE_STANDS]
        available_landings = [f"Spline_{x}" for x in LANDING_SOURCES]
        available_departing = [f"Spline_{DEPARTURE_SPLINE}"]

        # Build all landing paths:
        # LandingSpline -> MasterSpline slice -> StandSpline (reversed)
        paths = []
        start_link = 0
        for landing_spline in available_landings:

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
                
                # Compute the master spline slice between the landing index and the stand index.
                # !!! EDGE CASE !!! - Spline C3 needs to be reversed
                if stand_spline == "Spline_C3":
                    master_edges = find_master_edges(start_link=end_link, end_link=start_link)
                else:
                    master_edges = find_master_edges(start_link=start_link, end_link=end_link)

                # Build final path
                # - Landing Spline Full (0 --> 1)
                # - Master Spline Edges
                # - Stand Spline Reversed (1 --> 0)
                segments = []
                segments.append({
                    "name": landing_spline,
                    "t_start": 0.0,
                    "t_end": 1.0,
                })

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

                # Remove prefixes to build path naming convention
                landing_id = landing_spline.replace("Spline_", "")
                stand_id = stand_spline.replace("Spline_", "")
                path_name = f"Path_{landing_id}_{stand_id}"
                
                # Append to paths list
                paths.append({
                    "name": path_name,
                    "source": landing_id,
                    "destination": stand_id,
                    "segments": segments,
                })
            
            # Advance the next landing spline index
            start_link += 1

        self.landing_paths = paths
        paths = []

        # Build all departing paths:
        #   StandSpline -> MasterSpline slice -> DepartureSpline
        for stand_spline in available_stands:
            start_link = None
            end_link = len(self.master_edges)

            # Find the master knot index that connects to this stand spline.
            for n, link in self.master_links.items():
                if stand_spline in link:
                    start_link = int(n)
                
                if start_link is None:
                    continue
                    
            # Slice the master spline from the stand index to the end (towards Departure).
            master_edges = find_master_edges(start_link=start_link, end_link=end_link)
            segments = []

            # Stand spline (0 --> 1)
            segments.append({
                "name": stand_spline,
                "t_start": 0.0,
                "t_end": 1.0
            })

            # Append the master spline slice
            if master_edges:
                segments.append({
                    "name": MASTER_SPLINE,
                    "t_start": master_edges[0]["t_start"],
                    "t_end": master_edges[-1]["t_end"]
                })

            departure_hold_t = self._departure_hold_t()
            
            # Departure Spline (0 --> 1)
            segments.append({
                "name": "Spline_Departure",
                "t_start": 0.0,
                "t_end": 1.0,
                "departure_hold_t": departure_hold_t,
            })

            # Remove prefixes for path naming convention
            departing_id = "Departure"
            stand_id = stand_spline.replace("Spline_", "")
            path_name = f"Path_{stand_id}_{departing_id}"

            paths.append({
                "name": path_name,
                "source": stand_id,
                "destination": departing_id,
                "segments": segments
            })

        # Expose the final combined path list
        self.departing_paths = paths
        self.paths = self.landing_paths + self.departing_paths
