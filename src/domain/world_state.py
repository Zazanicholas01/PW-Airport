from __future__ import annotations
import logging

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    @staticmethod
    def from_payload(payload: Any) -> "Vec3 | None":

        # Validate payload to be a dictionary and to exist
        if payload is None or not isinstance(payload, dict):
            return None
        
        # Validate payload keys to have all x, y and z
        if not all(k in payload for k in ("x", "y", "z")):
            return None
        
        # Convert all values to floating points if possible
        try:
            return Vec3(float(payload["x"]), float(payload["y"]), float(payload["z"]))
        except (TypeError, ValueError):
            return None
    
    def to_payload(self) -> dict[str, float]:
        """Serialize a Vec3 object back to a JSON dictionary"""
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass
class PlaneOnStand:
    stand_id: str
    prefab: str
    spawn_position: Vec3 | None
    spawned_at_utc: datetime
    last_position: Vec3 | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize state, convert datetimes to ISO strings and Vec3 to dictionaries"""
        return {
            "stand_id": self.stand_id,
            "prefab": self.prefab,
            "spawn_position": None if self.spawn_position is None else self.spawn_position.to_payload(),
            "spawned_at_utc": self.spawned_at_utc.isoformat(),
            "last_position": None if self.last_position is None else self.last_position.to_payload(),
        }


class WorldState:
    def __init__(self):
        self._planes_by_stand: dict[str, PlaneOnStand] = {}


    def record_plane_spawn(self, *, stand_id: str, prefab: str, position: dict | None):
        """Create PlaneOnStand record with idempotency enforcing rules"""

        # Idempotency enforcing rule
        existing = self._planes_by_stand.get(stand_id)
        if existing is not None:
            return existing

        # Get spawn position by serializing payload position into Vec3 object
        spawn_position = Vec3.from_payload(position)

        # Create Plane On Stand record with last position as spawn position
        plane = PlaneOnStand(
            stand_id=stand_id,
            prefab=prefab,
            spawn_position=spawn_position,
            spawned_at_utc=utc_now(),
            last_position=spawn_position,
        )

        # Save it into World State dictionary, Logging and return the record
        self._planes_by_stand[stand_id] = plane
        logging.debug("[world_state] spawn recorded stand=%s prefab=%s total=%d", stand_id, prefab, len(self._planes_by_stand))
        return plane
    

    def get_plane_on_stand(self, stand_id: str) -> PlaneOnStand | None:
        return self._planes_by_stand.get(stand_id)
    

    def list_planes_on_stand(self) -> list[PlaneOnStand]:
        return list(self._planes_by_stand.values())


    def to_dict(self) -> dict[str, Any]:
        return {"planes_on_stands": [p.to_dict() for p in self.list_planes_on_stands()]}


    def count_planes(self) -> int:
        return len(self._planes_by_stand)


    def debug_summary(self) -> str:
        items = sorted(self._planes_by_stand.values(), key=lambda p:p.stand_id)
        parts = [f"{p.stand_id}:{p.prefab}" for p in items]
        return f"planes={len(items)} [{', '.join(parts)}]"
