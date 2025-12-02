class InitGraph:
    def __init__(self, airport_id: str = "LIAG"):
        self.master_nodes = []
        self.master_edges = []
        self.master_spline = []
        self.splines = []
        self.airport_id = airport_id

    # Parsing splines without nodes
    # Constructing master nodes and edges from master spline
