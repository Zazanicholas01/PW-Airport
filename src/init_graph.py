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
    
    def add_master_spline(self, spline) -> None:
        """Add the master spline payload."""
        self.master_spline = spline
        self.construct_master_links()

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

        print("Master Links Constructed: ", self.master_links)

