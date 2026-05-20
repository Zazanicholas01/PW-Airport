import logging, random
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session, sessionmaker

from src.db.engine import get_engine
from src.db import models

from src.transport.command_builders import build_spawn_plane

from src.domain.status_constants import FLIGHT_STATUS, PARKING_SPLINES, SPAWN_CONTEXT, STAND_STATUS


@dataclass
class StandState:
    """In-memory snapshot of a stand."""
    id: str
    status: str
    position: dict | None = None
    type: str | None = None


class SpawnScheduler:
    """Plan plane spawns and reserve stands during simulation bootstrap."""

    def __init__(self, prefab_store, commands, session_factory: sessionmaker | None = None) -> None:
        
        self.prefab_store = prefab_store
        self.Session = session_factory
        self.commands = commands

        self._stands_loaded = False
        self._stand_state: dict[str, StandState] = {}
        self.starting_n_prefabs = 3
        self._stands_reset = False


    def _reset_all_stands_once(self) -> None:
        """Set all stands to free_status once at simulation start"""

        # Check flag of stands reset for idempotency
        if self._stands_reset:
            return
        
        with self.Session() as session:

            # Cleanup in FK safe order. Reset stands / flights links, the delete dependent tables
            session.execute(
                update(models.Stand).values(status=STAND_STATUS.AVAILABLE, airplane_id=None,)
            )
            session.execute(update(models.Flight).values(airplane_id=None))
            session.execute(
                update(models.Flight)
                .where(models.Flight.status != FLIGHT_STATUS.COMPLETED)
                .values(status=FLIGHT_STATUS.UNSCHEDULED)
            )
            session.execute(delete(models.Operation))
            
            # Reset Parking Sports instead of deleting them
            session.execute(
                update(models.ParkingSpot).values(
                    status=STAND_STATUS.AVAILABLE,
                    airplane_id=None,
                )
            )

            existing_parkings = set(
                session.scalars(select(models.ParkingSpot.spline)).all()
            )

            for parking_n in PARKING_SPLINES:
                if parking_n not in existing_parkings:
                    session.add(models.ParkingSpot(
                        airplane_id=None,
                        status=STAND_STATUS.AVAILABLE,
                        spline=parking_n,
                    ))

            session.execute(delete(models.Airplane))
            session.commit()
        
        # Set the flag for stands reset to avoid future executions
        self._stands_reset = True
        logging.info("[spawn scheduler] All stands reset to free status")


    def plan_initial_spawns(self) -> list[dict]:
        """Pick stands and prefabs for the initial spawn batch."""

        # Reset all stands once and ensure stand cache execution
        self._reset_all_stands_once()
        self._ensure_stand_cache()

        # Get random free stands and random plane prefabs
        stand_ids = self._pick_available_stand_ids(self.starting_n_prefabs)
        prefabs = self._pick_prefabs(count=self.starting_n_prefabs, allowed_type="plane")

        if not stand_ids or not prefabs:
            return []

        with self.Session() as session:
            spawn_commands = []

            # Loop over each stand / prefab pair
            for stand_id, prefab in zip(stand_ids, prefabs):

                # Reserve a stand
                self._reserve_stand(session, stand_id)

                # Get stand position from cached stand state
                position = None
                if stand_id in self._stand_state:
                    position = self._stand_state[stand_id].position
                
                # Generate random UUID string for the airplane
                airplane_id = str(uuid4())

                # Create spawn command with prefab / stand / position / airplane
                # Spawns with context of bootstrap
                spawn_commands.append(self.commands.spawn_plane(
                    prefab=prefab["name"],
                    stand_id=stand_id,
                    position=position,
                    airplane_id=airplane_id,
                    spawn_context=SPAWN_CONTEXT.BOOTSTRAP,
                ))

            session.commit()
            return spawn_commands


    def _ensure_stand_cache(self) -> None:
        """Load stand state once and keep it in memory."""
        
        # Check for stands loaded flag for idempotency
        if self._stands_loaded:
            return

        with self.Session() as session:

            # Get all stands from DB
            stands: Iterable[models.Stand] = session.scalars(select(models.Stand))
            
            # Create a snapshot of the stand following StandState structure
            snapshot = {
                stand.id: StandState(
                    id=stand.id,
                    status=stand.status,
                    position=getattr(stand, "position", None),
                    type=getattr(stand, "type", None),
                )
                for stand in stands
            }

        # Load snapshots and set idempotency flag
        self._stand_state = snapshot
        self._stands_loaded = True
        logging.info("[spawn scheduler] Loaded %d stands into scheduler cache", len(self._stand_state))


    def _pick_prefabs(self, count: int, *, allowed_type: str | None = None) -> list[dict]:
        """Randomly sample prefabs from the prefab store payloads."""

        # Check whether prefabs have been sent from Unity and saved
        if not self.prefab_store.prefabs:
            logging.warning("[spawn scheduler] No prefabs available for spawning")
            return []

        # Filter to match allowed type (Remove ground vehicles from candidates)
        candidates = list(self.prefab_store.prefabs)
        if allowed_type is not None:
            candidates = [
                prefab for prefab in candidates
                if str(prefab.get("type", "")).lower() == allowed_type
            ]
        
        # Sanity check for candidates to exist
        if not candidates:
            logging.warning("No prefabs available for spawning")
            return []

        # If candidates are less than the count needed, return all candidates
        if len(candidates) <= count:
            return candidates

        # If candidates more than count needed, random sample
        return random.sample(candidates, k=count)


    def _pick_available_stand_ids(self, count: int) -> list[str]:
        """Return a sample of stand IDs that are currently marked as free in cache."""

        # Filter only available stands
        candidates = [
            stand_id
            for stand_id, state in self._stand_state.items()
            if state.status == STAND_STATUS.AVAILABLE
        ]

        # If no free stands, return empty and log warning
        if not candidates:
            logging.warning("[spawn scheduler] No free stands available")
            return []

        # If candidates less than count, return all
        if len(candidates) <= count:
            return candidates

        # If candidates more than count, random sample
        return random.sample(candidates, k=count)


    def _reserve_stand(self, session: Session, stand_id: str) -> None:
        """Mark a stand as occupied in cache and persist the change."""

        # Update stand status to Occupied in cache
        state = self._stand_state.get(stand_id)
        if state is not None:
            state.status = STAND_STATUS.OCCUPIED

        # Update stand status to Occupied in DB
        session.execute(
            update(models.Stand)
            .where(models.Stand.id == stand_id)
            .values(status=STAND_STATUS.OCCUPIED)
        )
