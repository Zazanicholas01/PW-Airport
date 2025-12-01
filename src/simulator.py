class Simulator:
    def __init__(self):
        self.splines = []
        self.prefabs = []
    
    def add_spline(self, spline):
        """Add a single spline payload."""
        self.splines.append(spline)

    def add_splines(self, payload):
        """Add many splines from the given payload."""
        self.splines.extend(payload)

    def add_prefab(self, prefab):
        """Add a single prefab payload."""
        self.prefabs.append(prefab)

    def add_prefabs(self, payload):
        """Add many prefabs from the given payload."""
        self.prefabs.extend(payload)

    def print_contents(self):
        """Print current splines and prefabs for debugging."""
        print("Simulator splines:")
        print(self.splines)
        print("Simulator prefabs:")
        print(self.prefabs)
