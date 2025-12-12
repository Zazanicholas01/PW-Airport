import logging, asyncio

from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete, text

from src.database import get_engine
from src import models

class SetupState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.receiving_splines = False
        self.receiving_prefabs = False
        self.pending_splines: list[dict] = []
        self.pending_prefabs: list[dict] = []
        self.splines_committed = False
        self.prefabs_committed = False
        self.setup_completed = False
        self.path_building = False


class SetupBusHandler:
    """Handle setup / import events and batching via an async queue."""

    def __init__(self, simulator, init_graph) -> None:
        self.simulator = simulator
        self.init_graph = init_graph
        self.state = SetupState()
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self.engine = get_engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
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
        """Enqueue a decoded JSON payload for processing."""
        await self.queue.put(payload)


    async def _event_loop(self) -> None:
        """Background task to process incoming events from the queue."""
        while True:
            payload = await self.queue.get()
            try:
                await self.handle_payload(payload)
            except Exception:
                logging.exception("Error Handling Payload: %r", payload)
            finally:
                self.queue.task_done()


    async def handle_payload(self, payload: dict) -> None:
        """Main handler for all JSON payloads coming from the queue."""
        if not isinstance(payload, dict):
            return

        if self.state.setup_completed:
            logging.info("Setup already completed; ignoring payload")
            return

        if payload.get("type") == "event":
            await self._handle_control_event(payload)

        if "spline" in payload:
            await self._buffer_spline(payload["spline"])
            return

        if "prefabs" in payload:
            await self._buffer_prefabs(payload["prefabs"])
            return


    async def _handle_control_event(self, evt_payload: dict) -> None:
        """Handle control events from Unity."""
        event_name = evt_payload.get("event")
        if event_name == "spline":
            return
        logging.info("Control Event Received: %s", event_name)

        if event_name == "setup-init":
            self.state.reset()
            logging.info("Setup init: State Reset")
            return

        if event_name == "send-splines":
            self.state.receiving_splines = True
            self.state.pending_splines.clear()
            logging.info("Begin Spline Batch")
            return

        if event_name == "finish-send-splines":
            self.state.receiving_splines = False
            await self._commit_splines()
            logging.info("Finished Spline Batch")
            return

        if event_name == "send-prefabs":
            self.state.receiving_prefabs = True
            self.state.pending_prefabs.clear()
            logging.info("Begin Prefab Batch")
            return

        if event_name == "finish-send-prefabs":
            self.state.receiving_prefabs = False
            await self._commit_prefabs()
            logging.info("Finished Prefab Batch")
            return


    async def _buffer_spline(self, spline: dict) -> None:
        """Buffer a single spline."""
        if not self.state.receiving_splines:
            logging.debug("Spline Ignored")
            return
        if not isinstance(spline, dict):
            logging.debug("Invalid Spline Payload")
            return
        self.state.pending_splines.append(spline)


    async def _commit_splines(self) -> None:
        """Commit buffered splines."""
        if not self.state.pending_splines:
            logging.info("No splines to Commit")
            return
        
        stand_positions: dict[str, dict] = {}

        for spline in self.state.pending_splines:

            name = spline.get("name", "<unnamed>")

            if name == "MasterSpline":
                self.init_graph.add_master_spline(spline)
                logging.info("Committed Master Spline")
                continue
            else:
                self.init_graph.add_spline(spline)

                last = spline.get("lastKnotPosition")
                if (
                    isinstance(last, dict)
                    and name.startswith("Spline_")
                    and all(k in last for k in ("x", "y", "z"))
                ):
                    stand_id = name.removeprefix("Spline_")
                    stand_positions[stand_id] = {
                        "x": last.get("x"),
                        "y": last.get("y"),
                        "z": last.get("z"),
                    }

        logging.info("Committed Splines")

        if stand_positions:
            with self.Session() as session:
                for stand_id, pos in stand_positions.items():
                    if stand_id not in ("AtterraggioLungo", "AtterraggioMedio", "AtterraggioCorto", "Decollo", "Parcheggio1", "Parcheggio2", "Parcheggio3"):
                        stand = session.get(models.Stand, stand_id)
                        if stand is None:
                            logging.warning("Stand not found")
                            continue
                        stand.position = pos
                session.commit()
            logging.info("Updated stand positions")

        #self.init_graph.print_master_spline()
        self.state.splines_committed = True
        self._check_setup_completion()


    async def _buffer_prefabs(self, prefabs) -> None:
        """Buffer multiple prefabs."""
        if not self.state.receiving_prefabs:
            logging.debug("Prefabs Ignored")
            return

        if not isinstance(prefabs, list):
            logging.info("Invalid Prefab Payload")
            return

        for prefab in prefabs:
            if not isinstance(prefab, dict):
                continue
            self.state.pending_prefabs.append(prefab)


    async def _commit_prefabs(self) -> None:
        """Commit buffered prefabs."""
        if not self.state.pending_prefabs:
            logging.info("No Prefabs to Commit")
            return

        self.simulator.add_prefabs(self.state.pending_prefabs)
        logging.info("Committed %d Prefabs", len(self.state.pending_prefabs))
        self.simulator.print_prefabs()
        self.state.prefabs_committed = True
        self._check_setup_completion()


    def _check_setup_completion(self) -> None:
        """Mark setup as complete once both prefabs and splines have been received."""
        if self.state.setup_completed:
            return
        
        if self.state.splines_committed and self.state.prefabs_committed:
            self.state.setup_completed = True
            logging.info("Setup completed; subsequent setup payloads will be ignored.")
            self.init_graph.build_paths()
            self.state.path_building = True

            if self.state.path_building:
                paths = []
                for path in self.init_graph.paths:
                    path = models.Percorso(
                        path_name=path["name"],
                        source=path["source"],
                        destination=path["destination"],
                        spline=path["segments"],
                    )
                    paths.append(path)

                with self.Session() as session:
                    session.execute(delete(models.Percorso))
                    session.execute(
                        text(
                            "SELECT setval(pg_get_serial_sequence('\"Percorso\"', 'id'), 1, false);"
                        )
                    )

                    session.add_all(paths)
                    session.commit()
                logging.info("Aggiunti Percorsi al DB")

        if self.state.splines_committed and self.state.prefabs_committed and self.state.path_building and self.state.setup_completed:
            self.setup_finished = True
