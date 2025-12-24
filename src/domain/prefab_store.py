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
        self.prefabs.append(prefab)

        name = prefab.get("name")
        if not isinstance(name, str) or not name:
            return
        self.prefab_by_name[name] = prefab

        if str(prefab.get("type", "")).lower() != "plane":
            return
        
        if name in self._plane_names:
            return
        
        try:
            airplane_type = type_for_airplane_model(name)
            airplane_range = range_for_airplane_model(name)
        except ValueError:
            return
        
        self._plane_names.add(name)
        self._planes_by_type_range[(airplane_type, airplane_range)].append(name)
        self._planes_by_type[airplane_type].append(name)
        self._planes_by_range[airplane_range].append(name)
    
    def add_prefabs(self, payload: list[dict]) -> None:
        for prefab in payload:
            if isinstance(prefab, dict):
                self.add_prefab(prefab)
    
    def pick_plane_prefab(self, flight_type: str | None, required_range: str | None) -> str | None:
        q = None
        if flight_type and required_range:
            q = self._planes_by_type_range.get((flight_type, required_range))
        if not q and flight_type:
            q = self._planes_by_type.get(flight_type)
        if not q and required_range:
            q = self._planes_by_range.get(required_range)
        
        if q:
            name = q[0]
            q.rotate(-1)
            return name
        
        for any_q in self._planes_by_type_range.values():
            if any_q:
                name = any_q[0]
                any_q.rotate(-1)
                return name
    
        return None

    def print_prefabs(self):
        for prefab in self.prefabs:
            print(prefab)