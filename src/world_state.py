from __future__ import annotations

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
        if payload is None or not isinstance(payload, dict):
            return None
        
        if not all(k in payload for k in ("x", "y", "z")):
            return None
        
        try:
            return Vec3(float(payload["x"]), float(payload["y"]), float(payload["z"]))
        except (TypeError, ValueError):
            return None
    
    def to_payload(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

@dataclass
class PlaneOnStand:
    stand_id: str
    prefab: str
    spawn_position: Vec3 | None
    spawned_at_utc: datetime
    last_position: Vec3 | None = None

    def to_dict(self) -> dict[str, Any]:
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
        existing = self._planes_by_stand.get(stand_id)
        if existing is not None:
            return existing

        spawn_position = Vec3.from_payload(position)
        plane = PlaneOnStand(
            stand_id=stand_id,
            prefab=prefab,
            spawn_position=spawn_position,
            spawned_at_utc=utc_now(),
            last_position=spawn_position,
        )
        self._planes_by_stand[stand_id] = plane
        return plane
    
    def get_plane_on_stand(self, stand_id: str) -> PlaneOnStand | None:
        return self._planes_by_stand.get(stand_id)
    
    def list_planes_on_stand(self) -> list[PlaneOnStand]:
        return list(self._planes_by_stand.values())

    def to_dict(self) -> dict[str, Any]:
        return {"planes_on_stands": [p.to_dict() for p in self.list_planes_on_stands()]}
