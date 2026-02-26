from collections import defaultdict, deque
from src.utils.mapping import range_for_airplane_model, type_for_airplane_model

class PrefabStore:
    def __init__(self):
        self.prefabs: list[dict] = []
        self.prefab_by_name: dict[str, dict] = {}

        self._plane_names: set[str] = set()
        self._planes_by_type_range: dict[tuple[str, str], deque[str]] = defaultdict(deque)
        self._planes_by_type: dict[str, deque[str]] = defaultdict(deque)
        self._planes_by_range: dict[str, deque[str]] = defaultdict(deque)


    def add_prefab(self, prefab: dict) -> None:
        """Store the prefab"""

        # Store the prefab into the Prefab Store
        self.prefabs.append(prefab)

        # Get the prefab name and perform sanity check and then save it in Prefab_By_Name data structure
        name = prefab.get("name")
        if not isinstance(name, str) or not name:
            return
        self.prefab_by_name[name] = prefab

        # Sanity check on prefabs to be only of type plane for now - TODO
        if str(prefab.get("type", "")).lower() != "plane":
            return
        
        # Deduplicate planes
        if name in self._plane_names:
            return
        
        # Mapping helpers to find type and range by airplane model
        try:
            airplane_type = type_for_airplane_model(name)
            airplane_range = range_for_airplane_model(name)
        except ValueError:
            return
        
        # Add the valid prefabs to the various data structures
        self._plane_names.add(name)
        self._planes_by_type_range[(airplane_type, airplane_range)].append(name)
        self._planes_by_type[airplane_type].append(name)
        self._planes_by_range[airplane_range].append(name)
    

    def add_prefabs(self, payload: list[dict]) -> None:
        """Add multiple prefabs from the batch payload from Unity"""

        for prefab in payload:

            # Sanity check on the prefab type and call to the Add_Prefab function
            if isinstance(prefab, dict):
                self.add_prefab(prefab)
    

    def pick_plane_prefab(self, flight_type: str | None, required_range: str | None) -> str | None:
        """Chose the best matching plane for the flight required"""

        # Search for all matching prefabs
        q = None
        if flight_type and required_range:
            q = self._planes_by_type_range.get((flight_type, required_range))
        if not q and flight_type:
            q = self._planes_by_type.get(flight_type)
        if not q and required_range:
            q = self._planes_by_range.get(required_range)
        
        # If found any, take first and rotate the list to ensure round-robin logic
        if q:
            name = q[0]
            q.rotate(-1)
            return name
        
        # If no range match found, FALLBACK to type selection with same logic
        for any_q in self._planes_by_type_range.values():
            if any_q:
                name = any_q[0]
                any_q.rotate(-1)
                return name
    
        return None
