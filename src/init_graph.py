import json, math
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
            self.master_links[i] = node.get('links', [])

        #print("Master Links Constructed: ", self.master_links)


    def extract_t_master_edges(self) -> None:
        """Extract the t parameters for master edges from the master spline."""

        knots = self.master_spline.get("knots", [])
        if not knots or len(knots) < 2:
            return None, None
        
        parameters = [knot.get("parameters", []) for knot in knots]
        X = [param[0]["x"] if param else None for param in parameters]

        ms_length = X[-1] - X[0]
        T = [round(abs(X[i] - X[0]) / ms_length, 2) for i in range(1, len(knots) - 1)]
        
        self.master_edges.append({"Name": "MS_01", "t_start": 0, "t_end": T[0]})
        for i in range(1, len(T) - 1):
            self.master_edges.append({"Name": f"MS_{i}{i+1}", "t_start": T[i-1], "t_end": T[i]})
        
        #print("Master Edges: ", self.master_edges)

