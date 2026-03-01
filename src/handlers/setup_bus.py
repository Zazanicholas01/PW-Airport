import logging, asyncio

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete, text, update

from src.db.engine import get_engine
from src.db import models
from src.domain.status_constants import *


@dataclass
class SetupState:
    """Mutable state for a single Unity setup/import run."""

    receiving_splines: bool = False
    receiving_prefabs: bool = False
    pending_splines: list[dict[str, Any]] = field(default_factory=list)
    pending_prefabs: list[dict[str, Any]] = field(default_factory=list)
    splines_committed: bool = False
    prefabs_committed: bool = False
    setup_completed: bool = False
    path_building: bool = False
    landing_spawn_position: dict[str, Any] | None = None

    def reset(self) -> None:
        """Reset all setup-related flags and clear buffers."""
        self.receiving_splines = False
        self.receiving_prefabs = False
        self.pending_splines.clear()
        self.pending_prefabs.clear()
        self.splines_committed = False
        self.prefabs_committed = False
        self.setup_completed = False
        self.path_building = False
        self.landing_spawn_position = None


class SetupBusHandler:
    """Handles setup payloads from Unity, Buffers them and commits them in batches via async queue loop"""

    def __init__(self, prefab_store, init_graph, *, session_factory: sessionmaker | None = None) -> None:

        self.prefab_store = prefab_store
        self.init_graph = init_graph
        self.state = SetupState()

        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

        self.Session = session_factory or sessionmaker(bind=get_engine(), future=True)

        self.setup_finished = False


    async def start(self) -> None:
        """Start the background event-processing loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._event_loop())


    async def stop(self) -> None:
        """Stop the background loop if it is running."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


    async def enqueue(self, payload: dict) -> None:
        """Pushes a decoded JSON payload into the internal async queue"""
        await self.queue.put(payload)


    async def _event_loop(self) -> None:
        """Consumer loop (Pulls payloads, processes them and marks the queue item done)"""

        while True:

            # Async consume of the payload
            payload = await self.queue.get()

            # Calls the payload handler as soon as it gets one
            try:
                await self.handle_payload(payload)

            except Exception:
                logging.exception("Error Handling Payload: %r", payload)
            finally:
                self.queue.task_done()


    async def handle_payload(self, payload: dict) -> None:
        """Main handler for all JSON payloads coming from the queue."""

        # Sanity check on the payload
        if not isinstance(payload, dict):
            return

        # Idempotency check on the setup completed flag
        if self.state.setup_completed:
            logging.info("[setup bus] Setup already completed; ignoring payload")
            return

        # Routes control event payloads to the right control event handler
        # Control events are: start / finish sending splines / prefabs
        if payload.get("type") == "event":
            await self._handle_control_event(payload)

        # Buffers spline payloads
        if "spline" in payload:
            await self._buffer_spline(payload["spline"])
            return

        # Buffers prefab payloads
        if "prefabs" in payload:
            await self._buffer_prefabs(payload["prefabs"])
            return


    async def _handle_control_event(self, evt_payload: dict) -> None:
        """Handle control events from Unity (start / finish sending splines / prefabs)"""

        # Get event type from the payload
        event_name = evt_payload.get("event")
        if event_name == "spline":
            return
        logging.info("[setup bus] Control Event Received: %s", event_name)

        # Handlers for every event type
        handlers = {
            "setup-init": self._evt_setup_init,
            "send-splines": self._evt_send_splines,
            "finish-send-splines": self._evt_finish_send_splines,
            "send-prefabs": self._evt_send_prefabs,
            "finish-send-prefabs": self._evt_finish_send_prefabs,
        }
        handler = handlers.get(event_name)

        # Sanity check on the handler selection
        if handler is None:
            logging.info("[setup bus] Unhandled control event: %s", event_name)
            return
        await handler()


    async def _evt_setup_init(self) -> None:
        """SETUP INIT EVENT HANDLER"""
        self.state.reset()
        logging.info("[setup bus] Setup init: State Reset")
    

    async def _evt_send_splines(self) -> None:
        """SEND SPLINES EVENT HANDLER"""
        self.state.receiving_splines = True
        self.state.pending_splines.clear()
        logging.info("[setup bus] Begin Spline Batch")


    async def _evt_finish_send_splines(self) -> None:
        """FINISH SEND SPLINES EVENT HANDLER"""
        self.state.receiving_splines = False
        await self._commit_splines()
        logging.info("[setup bus] Finished Spline Batch")


    async def _evt_send_prefabs(self) -> None:
        """SEND PREFABS EVENT HANDLER"""
        self.state.receiving_prefabs = True
        self.state.pending_prefabs.clear()
        logging.info("[setup bus] Begin Prefab Batch")


    async def _evt_finish_send_prefabs(self) -> None:
        """FINISH SEND PREFABS EVENT HANDLER"""
        self.state.receiving_prefabs = False
        await self._commit_prefabs()
        logging.info("[setup bus] Finished Prefab Batch")


    async def _buffer_spline(self, spline: dict) -> None:
        """Buffer a single spline."""

        # Ignores spline payloads based on receiving splines flag
        if not self.state.receiving_splines:
            logging.debug("[setup bus] Spline Ignored")
            return
        
        # Sanity check of validity of the spline payload
        if not isinstance(spline, dict):
            logging.debug("[setup bus] Invalid Spline Payload")
            return
        
        # Appends spline to the spline buffer
        self.state.pending_splines.append(spline)


    async def _commit_splines(self) -> None:
        """Commit buffered splines."""

        # Check if there is any pending spline to commit
        if not self.state.pending_splines:
            logging.info("[setup bus] No splines to commit")
            return
        
        # Build a map of stand_id -> position derived from spline first-knot positions
        stand_positions = self._commit_splines_to_graph(self.state.pending_splines)
        logging.info(f"[setup bus] Committed splines {len(self.state.pending_splines)}")
        self.state.pending_splines.clear()

        # Update stand position in DB and commits
        if stand_positions:
            self._persist_stand_positions(stand_positions)

        # Mark spline phase completed and trigger completion check
        self.state.splines_committed = True
        self._check_setup_completion()


    async def _buffer_prefabs(self, prefabs) -> None:
        """Buffer multiple prefabs."""

        # Check on receiving prefabs check for idempotency
        if not self.state.receiving_prefabs:
            logging.debug("[setup bus] Prefabs Ignored")
            return

        # Sanity check on prefabs to be a list
        if not isinstance(prefabs, list):
            logging.info("[setup bus] Invalid Prefab Payload")
            return

        # Filter with sanity check on single prefab payloads to be dictionaries and buffers them to commit
        for prefab in prefabs:
            if not isinstance(prefab, dict):
                continue
            self.state.pending_prefabs.append(prefab)


    async def _commit_prefabs(self) -> None:
        """Commit buffered prefabs."""

        # No commit if no prefabs have been buffered
        if not self.state.pending_prefabs:
            logging.info("[setup bus] No Prefabs to Commit")
            return

        # Add prefabs to prefab store
        self.prefab_store.add_prefabs(self.state.pending_prefabs)
        logging.info(f"[setup bus] Committed {len(self.state.pending_prefabs)} Prefabs")
        self.state.pending_prefabs.clear()

        # Mark prefab phase complete and trigger completion check
        self.state.prefabs_committed = True
        self._check_setup_completion()


    @staticmethod
    def _is_vec3(payload: Any) -> bool:
        return isinstance(payload, dict) and all(k in payload for k in ("x", "y", "z"))
    
    @staticmethod
    def _vec3(payload: dict[str, Any]) -> dict[str, Any]:
        return {"x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z")}
    

    def _commit_splines_to_graph(self, splines):
        """Commit spline definitions into the graph and extract stand positions"""

        stand_positions: dict[str, dict[str, Any]] = {}

        for spline in splines:
            name = spline.get("name", "<unnamed>")

            # Route to specific handler for Master Spline only
            if name == MASTER_SPLINE:
                self.init_graph.add_master_spline(spline)
                logging.info("[setup bus] Committed Master Spline")
                continue

            # For non-master splines route to add_spline method and get first knot position from Unity payload
            self.init_graph.add_spline(spline)
            first = spline.get("firstKnotPos")

            # Get and save landing spawn position from Spline_LongLanding (same position for every landing spline)
            if (
                self.state.landing_spawn_position is None
                and name == f"Spline_{LONG_LANDING_SPLINE}"
                and self._is_vec3(first)
            ):
                self.state.landing_spawn_position = self._vec3(first)
                logging.info(
                    "[setup bus] captured landing_spawn_position=%s",
                    self.state.landing_spawn_position,
                )

            # Save stand position from spline's first knot position
            if name.startswith("Spline_") and self._is_vec3(first):
                stand_id = name.removeprefix("Spline_")
                stand_positions[stand_id] = self._vec3(first)
        
        return stand_positions


    def _persist_stand_positions(self, stand_positions) -> None:
        """Save stand positions in DB"""

        updated = 0
        with self.Session() as session:
            with session.begin():
                for stand_id, pos in stand_positions.items():

                    # Skip non stand splines
                    if stand_id in EXCLUDED_STAND_IDS:
                        continue

                    # Get stand from DB
                    stand = session.get(models.Stand, stand_id)
                    if stand is None:
                        logging.warning(f"[setup bus] Stand not found: {stand_id}")
                    
                    stand.position = pos
                    updated += 1
        
        logging.info(f"[setup bus] Updated stand positions {updated}")


    def _check_setup_completion(self) -> None:
        """Mark setup as complete once both prefabs and splines have been received."""

        # Idempotency control on setup completed
        if self.state.setup_completed:
            return
        
        # Check on both splines and prefabs committed successfully
        if self.state.splines_committed and self.state.prefabs_committed:

            # Set setup completed flag
            self.state.setup_completed = True
            logging.info("[setup bus] Setup completed; subsequent setup payloads will be ignored.")

            # Trigger path building in init_graph and convert to ORM Path Models
            paths = self._build_path_models()

            # Truncate previous path records and build again
            self._rebuild_paths_in_db(paths)

        # Set final ready flag once all phases have been marked as done
        if self.state.splines_committed and self.state.prefabs_committed and self.state.path_building and self.state.setup_completed:
            self.setup_finished = True


    def _build_path_models(self) -> list[models.Path]:
        """Convert computed paths from init graph into ORM Path models"""

        # Trigger path building and set path building flag
        self.init_graph.build_paths()
        self.state.path_building = True

        # Convert into ORM Models
        paths: list[models.Path] = []
        for path in self.init_graph.paths:
            paths.append(
                models.Path(
                    path_name=path["name"],
                    source=path["source"],
                    destination=path["destination"],
                    spline=path["segments"],
                )
            )
        
        return paths


    def _rebuild_paths_in_db(self, paths: list[models.Path]) -> None:
        """Truncates previous paths from DB and builds again"""

        with self.Session() as session:
            with session.begin():

                # Records deleted with FK safe ordering and dependent tables wiping
                session.execute(update(models.Airplane).values(route_id=None))
                session.execute(update(models.Vehicle).values(route_id=None))
                session.execute(delete(models.Path))
                session.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence('\"Percorso\"', 'id'), 1, false);"
                    )
                )
                session.add_all(paths)
        
        logging.info(f"[setup bus] Aggiunti Percorsi al DB {len(paths)}")
