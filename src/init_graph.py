class InitGraph:
    def __init__(self, airport_id: str = "LIAG"):
        self.master_nodes = []
        self.master_edges = []
        self.master_spline = []
        self.splines = []
        self.airport_id = airport_id

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

