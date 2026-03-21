from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import time

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
        """Expose the current time scale"""
        return self._time_scale
    
    def now(self) -> datetime:
        """Computes the current simulated datetime"""
        # Get current time
        mono_now = time.monotonic()

        # Calculate time elapsed since simulation real time start and apply time scale
        dt_real = mono_now - self._mono_base
        dt_sim = dt_real * self._time_scale

        # Add to sim base and return current simulated time
        return self._sim_base + timedelta(seconds=dt_sim)
    

    def set_time_scale(self, new_scale: float) -> None:
        """Set Time Scale"""

        new_scale = float(new_scale)

        # Get current datetime
        current_sim = self.now()
        self._sim_base = current_sim

        # Get current real time and apply timescale
        self._mono_base = time.monotonic()
        self._time_scale = new_scale
    

    def set_sim_time(self, new_sim: datetime) -> None:
        """Set simulation time for time jumps - TODO"""

        # Sanity check on timezone awareness of the datetime
        if new_sim.tzinfo is None:
            raise ValueError("New sim must be timezone aware")
        
        # Reset monotonic base so that the new set time becomes now
        self._sim_base = new_sim
        self._mono_base = time.monotonic()
    

    def make_sync(self) -> ClockSync:
        """Increment Sync ID to return a ClockSync object"""

        # Increment sync ID
        self._sync_id += 1

        # Read current sim time and convert to unix milliseconds
        sim = self.now()
        sim_unix_ms = int(sim.timestamp() * 1000)

        return ClockSync(sync_id=self._sync_id, sim_unix_ms=sim_unix_ms, time_scale=self._time_scale)
