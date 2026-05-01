import asyncio, logging
import math
from datetime import timedelta

from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from functools import lru_cache

from src.services.flight_generator import RandomFlightGenerator
from src.db import models

from src.db.engine import get_engine
from src.utils.event_log import append_event

from src.domain.status_constants import *

from src.path_commands import make_continue_path_command

from src.utils.mapping import landing_source_for_range

@lru_cache()
def _default_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), future=True)


class RuntimeBusHandler:
    def __init__(
        self,
        prefab_store,
        session_factory: sessionmaker | None = None,
        *,
        bus = None,
        commands = None,
        clock=None,
        clock_lock: asyncio.Lock | None = None,
        clock_changed: asyncio.Event | None = None,
        disembark_sim_seconds: float = float(DISEMBARK_SIM_SECONDS),
    ):
        self.prefab_store = prefab_store
        self.queue = asyncio.Queue()
        self._task = None

        self.Session = session_factory or _default_sessionmaker()
        self._flight_generator = RandomFlightGenerator(self.Session)

        self._disembark_tasks: dict[str, asyncio.Task] = {}
        self._disembark_sim_seconds = float(disembark_sim_seconds)

        self._clock = clock
        self._clock_lock = clock_lock
        self._clock_changed = clock_changed

        self._bus = bus
        self._commands = commands

    
    def _start_disembark_timer(self, airplane_id: str) -> None:
        """Reset and start Disembarking Timer"""

        # Ensures only one timer per airplane, cleaning up eventual old ones
        old = self._disembark_tasks.pop(airplane_id, None)
        if old is not None:
            old.cancel()
        
        # Starts the async timer that will change status Disembarking --> Parked / Completed
        self._disembark_tasks[airplane_id] = asyncio.create_task(self._finish_disembark(airplane_id))
    

    async def _sleep_sim_seconds(self, seconds: float) -> None:
        """Sleep timer in simulated time"""

        # Validation only for positive time
        if seconds <= 0:
            return

        # Get clock if available, FALLBACK to simple asyncio sleep
        clock = self._clock
        if clock is None:
            await asyncio.sleep(seconds)
            return

        # Set the wake up target, starting by now
        if self._clock_lock is None:
            target = clock.now() + timedelta(seconds=seconds)
        else:
            async with self._clock_lock:
                target = clock.now() + timedelta(seconds=seconds)

        while True:

            # Read current time and time scale
            if self._clock_lock is None:
                now = clock.now()
                time_scale = float(getattr(clock, "time_scale", 1.0))
            else:
                async with self._clock_lock:
                    now = clock.now()
                    time_scale = float(getattr(clock, "time_scale", 1.0))

            # Convert to seconds and exit when simulated target is reached
            remaining_sim_s = (target - now).total_seconds()
            if remaining_sim_s <= 0:
                return

            # Sleep timeout (10ms - 1s)
            if (not math.isfinite(time_scale)) or time_scale <= 0.0:
                timeout = 1.0
            else:
                timeout = min(1.0, max(0.01, remaining_sim_s / time_scale))

            # If there is no event to wait on, use normal sleeping
            if self._clock_changed is None or self._clock_changed.is_set():
                await asyncio.sleep(timeout)
                continue

            # Wait for clock changed events or sleep timeout to trigger another poll
            try:
                await asyncio.wait_for(self._clock_changed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass


    async def _finish_disembark(self, airplane_id: str) -> None:
        """Completing disembarking task Disembarking --> Completed"""

        try:
            # Wait the configured disembark seconds
            await self._sleep_sim_seconds(self._disembark_sim_seconds)

            with self.Session() as session:

                # Get airplane and ensure status is Disembarking
                airplane = session.get(models.Airplane, airplane_id)
                if airplane is None:
                    return
                if getattr(airplane, "status", None) != AIRPLANE_STATUS.DISEMBARKING:
                    return
                
                # Update status from Disembarking to Parked
                airplane.status = AIRPLANE_STATUS.PARKED

                # Update also the flight linked to that airplane from Disembarking to Completed
                flight = session.scalars(
                    select(models.Flight)
                    .where(models.Flight.airplane_id == airplane_id)
                    .where(models.Flight.status.in_((FLIGHT_STATUS.DISEMBARKING, FLIGHT_STATUS.LANDING)))
                    .order_by(models.Flight.arrival_time.desc())
                ).first()

                if flight is not None:
                    flight.status = FLIGHT_STATUS.COMPLETED

                session.commit()
            
            # Final logging and exception handling

            logging.info("[runtime] disembark complete airplane_id=%s -> Parked", airplane_id)
            append_event({
                "type": "backend_event",
                "event": "disembark_complete",
                "airplane_id": airplane_id,
            })
        except asyncio.CancelledError:
            return
        except Exception:
            logging.exception("[runtime] disembark timer failed airplane_id=%s", airplane_id)


    async def start(self):
        """Launch the background consumer task"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._event_loop())
    

    async def enqueue(self, payload: dict):
        """Entrypoint to push a payload into the async queue"""
        await self.queue.put(payload)
    

    async def _event_loop(self):
        """Consume forever loop"""
        while True:
            payload = await self.queue.get()
            try:
                await self.handle_payload(payload)
            finally:
                self.queue.task_done()
    

    def _find_stand_id_by_airplane_id(self, session, airplane_id: str) -> str | None:
        """Helper DB Function to lookup at which stand currently references this airplane"""

        return session.execute(select(models.Stand.id).where(models.Stand.airplane_id == airplane_id)).scalar_one_or_none()


    async def handle_payload(self, payload: dict):
        """Payload Handling event router"""

        # Sanity check on payload to be of type event
        if payload.get("type") != "event":
            return

        # Get event type and airplane ID
        evt = payload.get("event")
        airplane_id = payload.get("airplane_id")
        if not isinstance(airplane_id, str) or not airplane_id:
            return

        with self.Session() as session:

            # Get stand linked to the airplane
            stand_id = self._find_stand_id_by_airplane_id(session, airplane_id)

            # Path Completed Event Handling
            if evt == RUNTIME_EVENTS.PATH_COMPLETED:

                # Get airplane by ID and sanity check on route exists
                airplane = session.get(models.Airplane, airplane_id)
                if airplane is None or getattr(airplane, "route_id", None) is None:
                    return
                
                # Get path by route linked to the airplane
                path = session.get(models.Path, airplane.route_id)
                if path is None:
                    return
                
                # Get destination of the path
                destination = getattr(path, "destination", None)

                # Retrieve parking number
                parking_n = self._parking_number_from_destination(destination)

                if parking_n is not None:
                    
                    # Retrieve parking from DB
                    parking = session.execute(
                        select(models.ParkingSpot)
                        .where(models.ParkingSpot.spline == parking_n)
                        .where(models.ParkingSpot.airplane_id == airplane_id)
                    ).scalars().first()

                    if parking is not None:
                        parking.status = STAND_STATUS.OCCUPIED
                    
                    # Update Airplane status
                    airplane.status = AIRPLANE_STATUS.IN_PARKING

                    session.commit()

                    logging.info(
                        "[runtime] path_completed (parking) airplane_id=%s parking=%s",
                        airplane_id,
                        parking_n,
                    )

                    # Send event to dashboard web
                    append_event({
                        "type": "backend_event",
                        "event": "parking_entered",
                        "airplane_id": airplane_id,
                        "parking_n": parking_n,
                        "route_id": airplane.route_id,
                    })

                    return
                
                if self._is_departure_destination(destination):
                    
                    # Update status of airplane from Departing --> InFlight with idempotency check
                    if airplane.status == AIRPLANE_STATUS.DEPARTING:
                        airplane.status = AIRPLANE_STATUS.IN_FLIGHT

                    # Get flight from DB and if exists, update status from Departing --> Dep_Ongoing
                    flight = session.scalars(
                        select(models.Flight)
                        .where(models.Flight.airplane_id == airplane_id)
                        .where(models.Flight.status.in_(FLIGHT_STATUS.DEPARTING_OUTBOUND))
                        .order_by(models.Flight.departure_time.desc())
                    ).first()

                    if flight is not None and flight.status != FLIGHT_STATUS.DEP_ONGOING:
                        flight.status = FLIGHT_STATUS.DEP_ONGOING
                    
                    session.commit()

                    # Send command to Unity through bus
                    if self._bus is not None and self._commands is not None:
                        await self._bus.send_command(
                            self._commands.despawn_plane(airplane_id=airplane_id)
                        )
                    
                    # Logging and return
                    logging.info("[runtime] path_completed (departure) airplane_id=%s route_id=%s", airplane_id, airplane.route_id)
                    append_event({
                        "type": "backend_event",
                        "event": "departure_completed",
                        "airplane_id": airplane_id,
                        "route_id": airplane.route_id,
                    })
                    return
                
                else:
                    # Update airplane status from Landing --> Disembarking
                    airplane.status = AIRPLANE_STATUS.DISEMBARKING

                    # Get flight linked to the airplane
                    flight = session.scalars(
                        select(models.Flight)
                        .where(models.Flight.airplane_id == airplane_id)
                        .where(models.Flight.status.in_((FLIGHT_STATUS.DISEMBARKING, FLIGHT_STATUS.LANDING)))
                        .order_by(models.Flight.arrival_time.desc())
                    ).first()

                    # Update flight status from Landing --> Disembarking
                    if flight is not None:
                        flight.status = FLIGHT_STATUS.DISEMBARKING

                    # Update stand status from Reserved --> Occupied
                    if stand_id is not None:
                        stand = session.get(models.Stand, stand_id)
                        if stand is not None and stand.airplane_id == airplane_id:
                            stand.status = STAND_STATUS.OCCUPIED
                    
                    # Commit session, Logging and Start disembarking timer
                    session.commit()
                    
                    logging.info("[runtime] path_completed (landing) airplane_id=%s -> Disembarking (timer started)", airplane_id)
                    append_event({
                        "type": "backend_event",
                        "event": "landing_completed",
                        "airplane_id": airplane_id,
                        "stand_id": stand_id,
                    })
                    self._start_disembark_timer(airplane_id)
                    return

            # Plane Left Stand Event Handling
            elif evt == RUNTIME_EVENTS.PLANE_LEFT_STAND:

                logging.info("[runtime] plane_left_stand received airplane_id=%s", airplane_id)

                # Sanity check on stand to be linked to the right airplane and to exist
                if stand_id is None:
                    logging.info("[runtime] plane_left_stand ignored airplane_id=%s reason=no linked stand", airplane_id)
                    return
                
                stand = session.get(models.Stand, stand_id)
                if stand is None or stand.airplane_id != airplane_id:
                    logging.info(
                        "[runtime] plane_left_stand ignored airplane_id=%s stand_id=%s reason=stand mismatch",
                        airplane_id,
                        stand_id,
                    )
                    return

                stand.airplane_id = None
                stand.status = STAND_STATUS.AVAILABLE
                session.commit()

                # Release stand logic
                released_stand_id = stand_id

                # Find parkings with a plane looping inside
                waiting_parking = self._find_waiting_parking(session)

                if waiting_parking is not None:

                    # Retrieve airplane ID and parking number
                    waiting_airplane_id = waiting_parking.airplane_id
                    parking_n = waiting_parking.spline

                    if isinstance(waiting_airplane_id, str):

                        # Reserve stand for the airplane
                        reserved = self._reserve_stand_for_waiting_airplane(
                            session,
                            stand_id=released_stand_id,
                            airplane_id=waiting_airplane_id,
                        )

                        if reserved:

                            # Assign parking exit path
                            route_id = self._assign_parking_exit_route(
                                session,
                                airplane_id=waiting_airplane_id,
                                parking_n=parking_n,
                                stand_id=released_stand_id,
                            )

                            if route_id is not None:

                                # Create continue path command
                                cmd = make_continue_path_command(
                                    airplane_id=waiting_airplane_id,
                                    session=session,
                                )

                                # Sanity check on the command to be right
                                if cmd is None:
                                    logging.warning("[runtime] parking clear aborted: continue_path command missing airplane_id=%s", waiting_airplane_id)
                                    session.rollback()
                                    return
                                
                                # Release the parking
                                waiting_parking.status = STAND_STATUS.AVAILABLE
                                waiting_parking.airplane_id = None
                                session.commit()

                                # Send continue path command
                                if cmd is not None and self._bus is not None:
                                    logging.info(
                                        "[runtime] sending continue_path airplane_id=%s route_id=%s segments=%s",
                                        waiting_airplane_id,
                                        cmd.get("route_id"),
                                        [segment.get("name") for segment in cmd.get("segments", [])],
                                    )
                                    await self._bus.send_command(cmd)

                                # Send clear parking command
                                if self._bus is not None and self._commands is not None:
                                    logging.info(
                                        "[runtime] sending clear_parking airplane_id=%s",
                                        waiting_airplane_id,
                                    )
                                    await self._bus.send_command(
                                        self._commands.clear_parking(
                                            airplane_id=waiting_airplane_id,
                                        )
                                    )

                                logging.info(
                                    "[runtime] parking cleared airplane_id=%s parking=%s stand_id=%s route_id=%s",
                                    waiting_airplane_id,
                                    parking_n,
                                    released_stand_id,
                                    route_id,
                                )

                                # Send event to dashboard web
                                append_event({
                                    "type": "backend_event",
                                    "event": "parking_cleared",
                                    "airplane_id": waiting_airplane_id,
                                    "parking_n": parking_n,
                                    "stand_id": released_stand_id,
                                    "route_id": route_id,
                                })


                logging.info("[runtime] plane_left_stand released stand_id=%s airplane_id=%s", stand_id, airplane_id)
                append_event({
                    "type": "backend_event",
                    "event": "plane_left_stand",
                    "airplane_id": airplane_id,
                    "stand_id": stand_id,
                })
                return
            
            elif evt == "parking_entered":

                # Retrieve parking spline and number
                parking_spline = payload.get("parking_spline")
                parking_n = self._parking_number_from_spline_name(parking_spline)

                if parking_n is None:
                    logging.warning("[runtime] parking_entered ignored invalid spline=%s airplane_id=%s", parking_spline, airplane_id)
                    return
                
                # Retrieve parking from DB
                parking = session.execute(
                    select(models.ParkingSpot)
                    .where(models.ParkingSpot.spline == parking_n)
                    .where(models.ParkingSpot.airplane_id == airplane_id)
                ).scalars().first()

                if parking is None:
                    logging.warning("[runtime] parking_entered no matching parking parking=%s airplane_id=%s", parking_n, airplane_id)
                    return
                
                # Mark parking as Occupied
                parking.status = STAND_STATUS.OCCUPIED

                # Retrieve airplane from DB and update status to IN_PARKING
                airplane = session.get(models.Airplane, airplane_id)
                if airplane is not None:
                    airplane.status = AIRPLANE_STATUS.IN_PARKING
                
                session.commit()

                logging.info("[runtime] parking_entered airplane_id=%s parking=%s", airplane_id, parking_n)
                return
            

    def _parking_number_from_spline_name(self, spline_name: str | None) -> int | None:

        if not isinstance(spline_name, str):
            return None
        
        # Search for Parking into spline name
        marker = "Parking"
        if marker not in spline_name:
            return None
        
        # Retrieve suffix from the spline name
        suffix = spline_name.split(marker, 1)[1]

        try:
            return int(suffix)
        except ValueError:
            return None
            

    def _parking_number_from_destination(self, destination: str | None) -> int | None:
        if not isinstance(destination, str):
            return None
        
        if not destination.startswith("Parking"):
            return None
        
        try:
            return int(destination.removeprefix("Parking"))
        except ValueError:
            return None
        
    def _find_waiting_parking(self, session):
        return session.execute(
            select(models.ParkingSpot)
            .where(models.ParkingSpot.status == "Occupied")
            .where(models.ParkingSpot.airplane_id.is_not(None))
            .order_by(models.ParkingSpot.id)
        ).scalars().first()

    def _reserve_stand_for_waiting_airplane(self, session, *, stand_id: str, airplane_id: str) -> bool:

        stand = session.get(models.Stand, stand_id)

        if stand is None:
            return False
        
        if stand.status != STAND_STATUS.AVAILABLE:
            return False
        
        stand.status = STAND_STATUS.RESERVED
        stand.airplane_id = airplane_id

        airplane = session.get(models.Airplane, airplane_id)
        if airplane is not None:
            airplane.status = AIRPLANE_STATUS.RESERVED

        flight = session.scalars(
            select(models.Flight)
            .where(models.Flight.airplane_id == airplane_id)
            .where(models.Flight.status == FLIGHT_STATUS.LANDING)
            .order_by(models.Flight.arrival_time.desc())
        ).first()

        if flight is not None:
            flight.status = FLIGHT_STATUS.LANDING
        
        return True

    def _assign_parking_exit_route(self, session, *, airplane_id: str, parking_n: int, stand_id: str) -> int | None:
        airplane = session.get(models.Airplane, airplane_id)
        if airplane is None:
            return None

        landing_id = landing_source_for_range(getattr(airplane, "range", None))
        source = f"Parking{parking_n}_{landing_id}"

        path_id = session.execute(
            select(models.Path.id)
            .where(models.Path.source == source)
            .where(models.Path.destination == stand_id)
        ).scalar_one_or_none()

        if path_id is None:
            logging.warning(
                "[runtime] parking exit path not found source=%s destination=%s airplane_id=%s",
                source,
                stand_id,
                airplane_id,
            )
            return None

        airplane.route_id = path_id
        return path_id
    

    def _is_departure_destination(self, destination: str | None) -> bool:

        if not isinstance(destination, str):
            return False
        
        return destination == "Departure" or destination.startswith("Departure_")
