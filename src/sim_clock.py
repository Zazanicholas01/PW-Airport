from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import time, logging

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

@dataclass
class ClockSync:
    sync_id: int
    sim_unix_ms: int
    time_scale: float

class SimulationClock:
    def __init__(self, *, sim_start: datetime | None = None, time_scale: float = 1.0):
        if sim_start is None:
            sim_start = utc_now()
        
        if sim_start.tzinfo is None:
            raise ValueError("Sim start must be timezone aware")
        
        self._sim_base = sim_start
        self._mono_base = time.monotonic()
        self._time_scale = float(time_scale)
        self._sync_id = 0
    
    @property
    def time_scale(self) -> float:
        return self._time_scale
    
    def now(self) -> datetime:
        mono_now = time.monotonic()
        dt_real = mono_now - self._mono_base
        dt_sim = dt_real * self._time_scale
        return self._sim_base + timedelta(seconds=dt_sim)
    
    def set_time_scale(self, new_scale: float) -> None:
        new_scale = float(new_scale)

        current_sim = self.now()
        self._sim_base = current_sim
        self._mono_base = time.monotonic()
        self._time_scale = new_scale
    
    def set_sim_time(self, new_sim: datetime) -> None:
        if new_sim.tzinfo is None:
            raise ValueError("New sim must be timezone aware")
        
        self._sim_base = new_sim
        self._mono_base = time.monotonic()
    
    def make_sync(self) -> ClockSync:
        self._sync_id += 1
        sim = self.now()
        sim_unix_ms = int(sim.timestamp() * 1000)
        logging.info(datetime.fromtimestamp(sim_unix_ms/1000, tz=timezone.utc).astimezone())

        return ClockSync(sync_id=self._sync_id, sim_unix_ms=sim_unix_ms, time_scale=self._time_scale)