import logging
import random
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from src.database import get_engine
from src import models


@dataclass
class StandState:
    """In-memory snapshot of a stand."""
    id: str
    status: str
    position: dict | None = None
    type: str | None = None


class SpawnScheduler:
    """Plan plane spawns and reserve stands during simulation bootstrap."""

    def __init__(self, simulator, session_factory: sessionmaker | None = None,
                free_status: str = "Libero",occupied_status: str = "Occupato",) -> None:
        
        self.simulator = simulator
        self.free_status = free_status
        self.occupied_status = occupied_status
        self.Session = session_factory or sessionmaker(bind=get_engine(), future=True)
        self._stands_loaded = False
        self._stand_state: dict[str, StandState] = {}
        self.starting_n_prefabs = 3
        self._stands_reset = False


    def _reset_all_stands_once(self) -> None:
        """Set all stands to free_status once at simulation start"""

        if self._stands_reset:
            return
        
        with self.Session() as session:
            session.execute(
                update(models.Stand).values(status=self.free_status)
            )
            session.commit()
        
        self._stands_reset = True
        logging.info("All stands reset to free status")


    def plan_initial_spawns(self) -> list[dict]:
        """Pick stands and prefabs for the initial spawn batch."""

        self._reset_all_stands_once()
        self._ensure_stand_cache()
        stand_ids = self._pick_available_stand_ids(self.starting_n_prefabs)
        prefabs = self._pick_prefabs(count=len(stand_ids))

        if not stand_ids or not prefabs:
            return []

        with self.Session() as session:
            spawn_commands = []
            for stand_id, prefab in zip(stand_ids, prefabs):
                self._reserve_stand(session, stand_id)
                position = None
                if stand_id in self._stand_state:
                    position = self._stand_state[stand_id].position
                spawn_commands.append(
                    {
                        "command": "spawn_plane",
                        "prefab": prefab["name"],
                        "stand_id": stand_id,
                        "position": position,
                    }
                )

            session.commit()
            return spawn_commands

    def _ensure_stand_cache(self) -> None:
        """Load stand state once and keep it in memory."""
        if self._stands_loaded:
            return

        with self.Session() as session:
            stands: Iterable[models.Stand] = session.scalars(select(models.Stand))
            snapshot = {
                stand.id: StandState(
                    id=stand.id,
                    status=stand.status,
                    position=getattr(stand, "position", None),
                    type=getattr(stand, "type", None),
                )
                for stand in stands
            }

        self._stand_state = snapshot
        self._stands_loaded = True
        logging.info("Loaded %d stands into scheduler cache", len(self._stand_state))

    def _pick_prefabs(self, count: int) -> list[dict]:
        """Randomly sample prefabs from the simulator payloads."""
        if not self.simulator.prefabs:
            logging.warning("No prefabs available for spawning")
            return []

        if count <= 0:
            return []

        if len(self.simulator.prefabs) <= count:
            return list(self.simulator.prefabs)

        return random.sample(self.simulator.prefabs, k=count)

    def _pick_available_stand_ids(self, count: int) -> list[str]:
        """Return a sample of stand IDs that are currently marked as free in cache."""
        free_stands = [
            stand_id
            for stand_id, state in self._stand_state.items()
            if state.status == self.free_status
        ]

        if not free_stands:
            logging.warning("No free stands available")
            return []

        if len(free_stands) <= count:
            return free_stands

        return random.sample(free_stands, k=count)

    def _reserve_stand(self, session: Session, stand_id: str) -> None:
        """Mark a stand as occupied in cache and persist the change."""
        state = self._stand_state.get(stand_id)
        if state is not None:
            state.status = self.occupied_status

        session.execute(
            update(models.Stand)
            .where(models.Stand.id == stand_id)
            .values(status=self.occupied_status)
        )
