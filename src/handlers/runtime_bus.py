import asyncio, logging
import math
from datetime import timedelta

from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from src.services.flight_generator import RandomFlightGenerator
from src.db import models

from src.db.engine import get_engine

_engine = get_engine()
Session = sessionmaker(bind=_engine, future=True)

DISEMBARK_SIM_SECONDS = 5 * 60

class RuntimeBusHandler:
    def __init__(
        self,
        prefab_store,
        session_factory: sessionmaker | None = None,
        *,
        clock=None,
        clock_lock: asyncio.Lock | None = None,
        clock_changed: asyncio.Event | None = None,
        disembark_sim_seconds: float = float(DISEMBARK_SIM_SECONDS),
    ):
        self.prefab_store = prefab_store
        self.queue = asyncio.Queue()
        self._task = None

        self.Session = session_factory or Session
        self._flight_generator = RandomFlightGenerator(self.Session)

        self._disembark_tasks: dict[str, asyncio.Task] = {}
        self._clock = clock
        self._clock_lock = clock_lock
        self._clock_changed = clock_changed
        self._disembark_sim_seconds = float(disembark_sim_seconds)

    
    def _start_disembark_timer(self, airplane_id: str) -> None:
        old = self._disembark_tasks.pop(airplane_id, None)
        if old is not None:
            old.cancel()
        
        self._disembark_tasks[airplane_id] = asyncio.create_task(self._finish_disembark(airplane_id))
    
    async def _sleep_sim_seconds(self, seconds: float) -> None:
        if seconds <= 0:
            return

        clock = self._clock
        if clock is None:
            await asyncio.sleep(seconds)
            return

        if self._clock_lock is None:
            target = clock.now() + timedelta(seconds=seconds)
        else:
            async with self._clock_lock:
                target = clock.now() + timedelta(seconds=seconds)

        while True:
            if self._clock_lock is None:
                now = clock.now()
                time_scale = float(getattr(clock, "time_scale", 1.0))
            else:
                async with self._clock_lock:
                    now = clock.now()
                    time_scale = float(getattr(clock, "time_scale", 1.0))

            remaining_sim_s = (target - now).total_seconds()
            if remaining_sim_s <= 0:
                return

            if (not math.isfinite(time_scale)) or time_scale <= 0.0:
                timeout = 1.0
            else:
                timeout = min(1.0, max(0.01, remaining_sim_s / time_scale))

            # `clock_changed` is shared with other loops (e.g. flight scheduler). Do not clear it here.
            # If it's already set, just sleep/poll; if it's not set, we can use it as an early wake-up.
            if self._clock_changed is None or self._clock_changed.is_set():
                await asyncio.sleep(timeout)
                continue

            try:
                await asyncio.wait_for(self._clock_changed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass


    async def _finish_disembark(self, airplane_id: str) -> None:
        try:
            await self._sleep_sim_seconds(self._disembark_sim_seconds)

            with self.Session() as session:
                airplane = session.get(models.Airplane, airplane_id)
                if airplane is None:
                    return
                if getattr(airplane, "status", None) != "Disembarking":
                    return
                
                airplane.status = "Parked"

                flight = session.scalars(
                    select(models.Flight)
                    .where(models.Flight.airplane_id == airplane_id)
                    .where(models.Flight.status.in_(("Disembarking", "Landing")))
                    .order_by(models.Flight.arrival_time.desc())
                ).first()

                if flight is not None:
                    flight.status = "Completed"

                session.commit()
            
            logging.info("[runtime] disembark complete airplane_id=%s -> Parked", airplane_id)
        except asyncio.CancelledError:
            return
        except Exception:
            logging.exception("[runtime] disembark timer failed airplane_id=%s", airplane_id)


    async def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._event_loop())
    

    async def enqueue(self, payload: dict):
        await self.queue.put(payload)
    

    async def _event_loop(self):
        while True:
            payload = await self.queue.get()
            try:
                await self.handle_payload(payload)
            finally:
                self.queue.task_done()
    

    def _find_stand_id_by_airplane_id(self, session, airplane_id: str) -> str | None:
        return session.execute(
            select(models.Stand.id).where(models.Stand.airplane_id == airplane_id)
        ).scalar_one_or_none()


    async def handle_payload(self, payload: dict):

        # Sanity check on payload to be of type event
        if payload.get("type") != "event":
            return

        # Get event type and airplane ID
        evt = payload.get("event")
        airplane_id = payload.get("airplane_id")
        if not isinstance(airplane_id, str) or not airplane_id:
            return

        with self.Session() as session:
            stand_id = self._find_stand_id_by_airplane_id(session, airplane_id)

            if evt == "path_completed":
                airplane = session.get(models.Airplane, airplane_id)
                if airplane is None or getattr(airplane, "route_id", None) is None:
                    return
                
                path = session.get(models.Path, airplane.route_id)
                if path is None:
                    return
                
                destination = getattr(path, "destination", None)
                
                if destination == "Departure":
                    logging.info("[runtime] path_completed (departure) airplane_id=%s route_id=%s", airplane_id, airplane.route_id)
                    return
                
                airplane.status = "Disembarking"

                flight = session.scalars(
                    select(models.Flight)
                    .where(models.Flight.airplane_id == airplane_id)
                    .where(models.Flight.status.in_(("Landing", "Disembarking")))
                    .order_by(models.Flight.arrival_time.desc())
                ).first()
                if flight is not None:
                    flight.status = "Disembarking"

                if stand_id is not None:
                    stand = session.get(models.Stand, stand_id)
                    if stand is not None and stand.airplane_id == airplane_id:
                        stand.status = "Occupied"
                
                session.commit()
                
                logging.info("[runtime] path_completed (landing) airplane_id=%s -> Disembarking (timer started)", airplane_id)
                self._start_disembark_timer(airplane_id)
                return

            if evt == "plane_left_stand":
                if stand_id is None:
                    return
                stand = session.get(models.Stand, stand_id)
                if stand is None or stand.airplane_id != airplane_id:
                    return

                stand.airplane_id = None
                stand.status = "Available"
                session.commit()
                return
