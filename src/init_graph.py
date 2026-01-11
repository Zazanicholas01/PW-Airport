import json
from pathlib import Path

class InitGraph:
    def __init__(self, airport_id: str = "LIAG"):
        self.master_nodes = []
        self.master_edges = []
        self.master_spline = []
        self.splines = []
        self.airport_id = airport_id
        self.master_links = {}

    # Parsing splines without nodes
    # Constructing master nodes and edges from master spline

    def add_splines(self, payload) -> None:
        """Add many splines from the given payload."""

        self.splines.extend(payload)
    
    def add_spline(self, spline) -> None:
        """Add a single spline payload."""

        self.splines.append(spline)
    
    def print_splines(self) -> None:
        """Print current splines for debugging."""

        print("Graph splines:")
        print(self.splines)
    
    def print_master_spline(self) -> None:
        print("Master Spline Knots: ")
        print(self.master_spline)
    
    def add_master_spline(self, spline) -> None:
        """Add the master spline payload."""

        self.master_spline = spline
        self.construct_master_links()
        self.extract_t_master_edges()

    def construct_master_links(self) -> None:
        """Construct a list of links between nodes and other splines"""

        schema_path = Path(__file__).resolve().parent.parent / "schema_nodi.json"
        try:
            with schema_path.open('r', encoding='utf-8') as f:
                links_schema = json.load(f)
        except FileNotFoundError as e:
            print("Schema file not found:", e)
            return
        except json.JSONDecodeError as e:
            print("Error decoding JSON schema:", e)
            return
        
        for i, node in enumerate(links_schema.get('nodes', [])):
            links = node.get('links', [])
            links = [f"Spline_{link}" for link in links]
            self.master_links[i] = links

        print("Master Links Constructed: ", self.master_links)


    def extract_t_master_edges(self) -> None:
        """Extract the t parameters for master edges from the master spline."""

        knots = self.master_spline.get("knotEntries", [])
        if not knots or len(knots) < 2:
            return None, None
        try:
            x_coords = [knot.get("parameters", [])[0]["x"] for knot in knots]
        except (KeyError, IndexError, TypeError):
            return

        ms_length = x_coords[-1] - x_coords[0]
        if ms_length <= 0:
            return
        
        t_values = [(x - x_coords[0]) / ms_length for x in x_coords]
        
        for i, (t_start, t_end) in enumerate(zip(t_values, t_values[1:]), start=1):
            self.master_edges.append(
                {
                    "name": f"MS_{i-1}{i}",
                    "t_start": t_start,
                    "t_end": t_end
                }
            )
        
        print("Master Edges: ", self.master_edges)


    def build_paths(self) -> None:
        """Building Paths based on Master Edges, Master Links and Splines"""
        
        def find_master_edges(start_link, end_link):
            """Returns the slicing of master edges between start link and end link"""

            if end_link == len(self.master_edges):
                return self.master_edges[start_link:]
            
            return self.master_edges[start_link:end_link]

        # Loop Atterraggio Lungo / Medio / Corto
        available_stands = ["O1", "O2", "O3", "O4", "O5", "P1", "P2", "P3", "C1", "C2", "C3"]
        available_landings = ["LongLanding", "MediumLanding", "ShortLanding"]
        available_departing = "Departure"

        available_stands = [f"Spline_{x}" for x in available_stands]
        available_landings = [f"Spline_{x}" for x in available_landings]
        available_departing = [f"Spline_Departure"]

        paths = []
        start_link = 0
        for landing_spline in available_landings:
            for stand_spline in available_stands:
                end_link = None
                for n, link in self.master_links.items():
                    if stand_spline in link:
                        end_link = int(n)
                        break    
                
                if end_link is None:
                    continue
                
                if stand_spline == "Spline_C3":
                    master_edges = find_master_edges(start_link=end_link, end_link=start_link)
                else:
                    master_edges = find_master_edges(start_link=start_link, end_link=end_link)

                segments = []
                segments.append({
                    "name": landing_spline,
                    "t_start": 0.0,
                    "t_end": 1.0,
                })

                if master_edges:
                    if start_link > end_link:
                        segments.append({
                            "name": "MasterSpline",
                            "t_start": master_edges[-1]["t_end"],
                            "t_end": master_edges[0]["t_start"],
                        })
                    else:
                        segments.append({
                            "name": "MasterSpline",
                            "t_start": master_edges[0]["t_start"],
                            "t_end": master_edges[-1]["t_end"],
                        })
                
                segments.append({
                    "name": stand_spline,
                    "t_start": 0.0,
                    "t_end": 1.0,
                })

                landing_id = landing_spline.replace("Spline_", "")
                stand_id = stand_spline.replace("Spline_", "")
                path_name = f"Path_{landing_id}_{stand_id}"
                
                paths.append({
                    "name": path_name,
                    "source": landing_id,
                    "destination": stand_id,
                    "segments": segments,
                })
            
            start_link += 1

        self.landing_paths = paths
        paths = []

        # Loop Decollo
        for stand_spline in available_stands:
            start_link = None
            end_link = len(self.master_edges)

            for n, link in self.master_links.items():
                if stand_spline in link:
                    start_link = int(n)
                
                if start_link is None:
                    continue
                    
            master_edges = find_master_edges(start_link=start_link, end_link=end_link)
            segments = []

            segments.append({
                "name": stand_spline,
                "t_start": 0.0,
                "t_end": 1.0
            })

            if master_edges:
                segments.append({
                    "name": "MasterSpline",
                    "t_start": master_edges[0]["t_start"],
                    "t_end": master_edges[-1]["t_end"]
                })
            
            segments.append({
                "name": "Spline_Departure",
                "t_start": 0.0,
                "t_end": 1.0
            })

            departing_id = "Departure"
            stand_id = stand_spline.replace("Spline_", "")
            path_name = f"Path_{stand_id}_{departing_id}"

            paths.append({
                "name": path_name,
                "source": stand_id,
                "destination": departing_id,
                "segments": segments
            })

        self.departing_paths = paths
        self.paths = self.landing_paths + self.departing_paths
