class Simulator:
    def __init__(self):
        self.prefabs = []

    def add_prefab(self, prefab):
        """Add a single prefab payload."""
        self.prefabs.append(prefab)

    def add_prefabs(self, payload):
        """Add many prefabs from the given payload."""
        self.prefabs.extend(payload)

    def print_prefabs(self):
        """Print current prefabs for debugging."""
        print("Simulator prefabs:")
        print(self.prefabs)
