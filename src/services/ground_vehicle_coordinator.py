from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from src.db import models

from src.domain.status_constants import BUS_SERVICE_CONFIG

# ============================
# HELPER FUNCTIONS
# ============================

def planned_services_for_flight_type(flight_type: str | None) -> list[str]:
    
    # passenger_transfer -> Bus
    # luggage_transfer -> Cargo
    # cargo_transfer -> Cargo

    normalized = (flight_type or "").strip().lower()

    if normalized == "cargo":
        return ["cargo_transfer"]

    return ["passenger_transfer", "luggage_transfer"]


def service_allowed_for_stand(*, stand_id: str, service_type: str) -> bool:

    # Check stand type and return available services
    prefix = stand_id[:1].upper()

    if prefix == "P":
        return service_type in {"passenger_transfer", "luggage_transfer"}

    if prefix == "C":
        return service_type == "cargo_transfer"

    if prefix == "O":
        return service_type in {"passenger_transfer", "luggage_transfer", "cargo_transfer"}

    return False


def required_vehicle_type_for_service(service_type: str) -> str:
    if service_type == "passenger_transfer":
        return "Bus"

    return "Cargo"


def vehicle_can_serve_stand(*, vehicle_type: str, stand_id: str) -> bool:
    prefix = stand_id[:1].upper()

    if vehicle_type == "Bus":
        return prefix in {"P", "O"}

    if vehicle_type == "Cargo":
        return prefix in {"P", "C", "O"}

    return False

def resolve_route_nodes(*, stand_id: str, service_type: str, returning: bool) -> tuple[str, str]:
    prefix = stand_id[:1].upper()

    if service_type == "passenger_transfer":
        home = "BusHome_P" if prefix == "P" else "BusHome_O"

    elif service_type == "luggage_transfer":
        if prefix == "P":
            home = "CargoHome_P"
        elif prefix == "O":
            home = "CargoHome_O"
        else:
            raise ValueError(f"Invalid luggage_transfer stand: {stand_id}")

    elif service_type == "cargo_transfer":
        if prefix == "C":
            home = "CargoHome_C"
        elif prefix == "O":
            home = "CargoHome_O"
        else:
            raise ValueError(f"Invalid cargo_transfer stand: {stand_id}")

    else:
        raise ValueError(f"Unknown service type: {service_type}")

    return (stand_id, home) if returning else (home, stand_id)


def resolve_capacity_workload(*, airplane, service_type: str) -> int:
    airplane_capacity = max(0, int(getattr(airplane, "capacity", 0) or 0))

    if service_type in {"passenger_transfer", "luggage_transfer", "cargo_transfer"}:
        return airplane_capacity

    return 0


@dataclass
class ActiveGroundJob:
    flight_id: str
    airplane_id: str
    stand_id: str
    service_sequence: list[str]
    current_index: int
    vehicle_id: str
    direction: str   # to_stand | servicing | to_home

    flow_mode: str   # load | unload
    current_service_total_units: int
    current_service_remaining_units: int


class GroundVehicleCoordinator:
    def __init__(
        self,
        Session,
        *,
        bus,
        commands,
        clock=None,
        clock_lock=None,
        clock_changed=None,
        service_durations: dict[str, float] | None = None,
    ):
        self.Session = Session
        self._bus = bus
        self._commands = commands
        self._clock = clock
        self._clock_lock = clock_lock
        self._clock_changed = clock_changed

        self._service_durations = service_durations or {
            "passenger_transfer": BUS_SERVICE_CONFIG.PASSENGER_TRANSFER_TIME,
            "luggage_transfer": BUS_SERVICE_CONFIG.LUGGAGE_TRANSFER_TIME,
            "cargo_transfer": BUS_SERVICE_CONFIG.CARGO_TRANSFER_TIME,
        }

        self._jobs_by_vehicle_id = {}
        self._jobs_by_flight_id = {}
        self._service_tasks = {}
    
    async def maybe_start_for_airplane(self, airplane_id: str) -> None:

        with self.Session() as session:

            # Get airplane from DB
            airplane = session.get(models.Airplane, airplane_id)
            if airplane is None:
                return
            
            # Get stand with airplane linked
            stand_id = session.execute(
                select(models.Stand.id).where(models.Stand.airplane_id == airplane_id)
            ).scalar_one_or_none()
            if stand_id is None:
                return
            
            # Get the flight from DB
            flight = session.scalars(
                select(models.Flight)
                .where(models.Flight.airplane_id == airplane_id)
                .order_by(models.Flight.departure_time.desc().nullslast(),
                          models.Flight.arrival_time.desc().nullslast())
            ).first()
            if flight is None:
                return
            
            if flight.id in self._jobs_by_flight_id:
                return
            
            # Retrieve flow mode (load or unload)
            flight_status = getattr(flight, "status", None)

            if flight_status == "Embarking":
                flow_mode = "load"
            elif flight_status == "Disembarking":
                flow_mode = "unload"
            else:
                return
            
            # Retrieve service sequence
            sequence = planned_services_for_flight_type(getattr(flight, "tipo", None))
            if not sequence:
                return
            
            # Check first service in the list
            first_service = sequence[0]
            total_units = resolve_capacity_workload(
                airplane=airplane,
                service_type=first_service,
            )
            if not service_allowed_for_stand(stand_id=stand_id, service_type=first_service):
                return
            
            # Pick vehicle for the service
            vehicle = self.pick_vehicle_for_service(
                session=session,
                stand_id=stand_id,
                service_type=first_service,
            )
            if vehicle is None:
                return
            
            # Create the job from the dataclass
            job = ActiveGroundJob(
                flight_id=flight.id,
                airplane_id=airplane_id,
                stand_id=stand_id,
                service_sequence=sequence,
                current_index=0,
                vehicle_id=vehicle.id,
                direction="to_stand",
                flow_mode=flow_mode,
                current_service_total_units=total_units,
                current_service_remaining_units=total_units,
            )

            await self.dispatch_job_phase(session=session, job=job, direction="to_stand")


    def pick_vehicle_for_service(self, *, session, stand_id: str, service_type: str):

        # Get vehicle based on type of service
        required_type = required_vehicle_type_for_service(service_type=service_type)

        # Retrieve available and compatible vehicles for the service
        vehicles = session.scalars(
            select(models.Vehicle)
            .where(models.Vehicle.type == required_type)
            .where(models.Vehicle.status == "Available")
            .order_by(models.Vehicle.id)
        ).all()

        for vehicle in vehicles:
            if vehicle_can_serve_stand(vehicle_type=required_type, stand_id=stand_id):
                return vehicle
        
        return None
    

    def assign_vehicle_route(self, *, session, vehicle_id: str, source: str, destination: str) -> int | None:

        # Retrieve path from DB
        path_id = session.execute(
            select(models.Path.id)
            .where(models.Path.source == source)
            .where(models.Path.destination == destination)
        ).scalar_one_or_none()

        if path_id is None:
            logging.warning(
                "[ground_ops] missing route vehicle_id=%s source=%s destination=%s",
                vehicle_id,
                source,
                destination,
            )
            return None
        
        # Retrieve vehicle and assign path
        vehicle = session.get(models.Vehicle, vehicle_id)
        if vehicle is None:
            return None
        
        vehicle.route_id = path_id
        return path_id


    async def dispatch_job_phase(self, *, session, job: ActiveGroundJob, direction: str) -> None:

        # Get service type
        service_type = job.service_sequence[job.current_index]

        source, destination = resolve_route_nodes(
            stand_id=job.stand_id,
            service_type=service_type,
            returning=(direction == "to_home"),
        )

        logging.info(
            "[ground_ops] dispatch phase vehicle_id=%s flight_id=%s service=%s direction=%s remaining=%s/%s route=%s->%s",
            job.vehicle_id,
            job.flight_id,
            service_type,
            direction,
            job.current_service_remaining_units,
            job.current_service_total_units,
            source,
            destination,
        )

        # Assign route to the vehicle
        route_id = self.assign_vehicle_route(
            session=session,
            vehicle_id=job.vehicle_id,
            source=source,
            destination=destination,
        )
        if route_id is None:
            session.rollback()
            logging.error(
                "[ground_ops] dispatch failed vehicle_id=%s flight_id=%s service=%s direction=%s route=%s->%s",
                job.vehicle_id,
                job.flight_id,
                service_type,
                direction,
                source,
                destination,
            )
            return
        
        # Get vehicle from DB
        vehicle = session.get(models.Vehicle, job.vehicle_id)
        if vehicle is None:
            logging.error(
                "[ground_ops] vehicle missing during dispatch vehicle_id=%s flight_id=%s",
                job.vehicle_id,
                job.flight_id,
            )
            return
        
        # Assign flight_id / destination / status
        vehicle.flight_id = job.flight_id
        vehicle.destination = destination
        vehicle.status = "EnRoute" if direction == "to_stand" else "Returning"

        session.commit()

        path = session.get(models.Path, route_id)
        if path is None or not path.spline:
            logging.error(
                "[ground_ops] path missing spline vehicle_id=%s route_id=%s direction=%s",
                job.vehicle_id,
                route_id,
                direction,
            )
            return
        
        # Attach speed profiles
        segments = self.attach_vehicle_speed_profiles(
            segments=path.spline,
            service_type=service_type,
            direction=direction,
        )
        
        # Commmit into job data structures
        job.direction = direction
        self._jobs_by_vehicle_id[job.vehicle_id] = job
        self._jobs_by_flight_id[job.flight_id] = job

        # Create and send start path command for the vehicle
        cmd = self._commands.start_vehicle_path(
            vehicle_id=job.vehicle_id,
            flight_id=job.flight_id,
            airplane_id=job.airplane_id,
            service_type=service_type,
            route_id=route_id,
            direction=direction,
            segments=segments,
        )

        logging.info(
            "[ground_ops] sending path command vehicle_id=%s route_id=%s direction=%s segments=%s",
            job.vehicle_id,
            route_id,
            direction,
            len(segments) if isinstance(segments, list) else "n/a",
        )

        await self._bus.send_command(cmd)


    async def handle_vehicle_arrived(self, vehicle_id: str) -> None:

        job = self._jobs_by_vehicle_id.get(vehicle_id)
        if job is None:
            return
        
        with self.Session() as session:
            vehicle = session.get(models.Vehicle, vehicle_id)
            if vehicle is None:
                return
            
            vehicle.status = "Servicing"
            vehicle_capacity = max(0, int(getattr(vehicle, "capacity", 0) or 0))
            session.commit()

        service_type = job.service_sequence[job.current_index]
        duration_seconds = self._service_durations.get(service_type, 300)

        batch_units = min(vehicle_capacity, job.current_service_remaining_units)

        label = (
            f"{service_type.replace('_', ' ').title()} "
            f"{job.current_service_total_units - job.current_service_remaining_units}"
            f"/{job.current_service_total_units}"
        )

        await self._bus.send_command({
            "command": "start_service_progress",
            "flight_id": job.flight_id,
            "airplane_id": job.airplane_id,
            "vehicle_id": job.vehicle_id,
            "stand_id": job.stand_id,
            "service_type": service_type,
            "duration_seconds": duration_seconds,
            "label": label,
        })
        
        job.direction = "servicing"
        self.start_service_timer(job)
        

    def start_service_timer(self, job: ActiveGroundJob) -> None:

        old = self._service_tasks.pop(job.vehicle_id, None)
        if old is not None:
            old.cancel()

        self._service_tasks[job.vehicle_id] = asyncio.create_task(
            self._finish_service_after_delay(job)
        )


    async def _finish_service_after_delay(self, job: ActiveGroundJob) -> None:
        service_type = job.service_sequence[job.current_index]
        seconds = self._service_durations.get(service_type, 300)

        try:
            await self.sleep_sim_seconds(seconds)

            with self.Session() as session:
                vehicle = session.get(models.Vehicle, job.vehicle_id)
                if vehicle is None:
                    return

                moved_units = min(
                    max(0, int(getattr(vehicle, "capacity", 0) or 0)),
                    job.current_service_remaining_units,
                )

                job.current_service_remaining_units = max(
                    0,
                    job.current_service_remaining_units - moved_units,
                )

            await self._bus.send_command({
                "command": "stop_service_progress",
                "stand_id": job.stand_id,
            })

            logging.info(
                "[ground_ops] service finished vehicle_id=%s flight_id=%s service=%s moved=%s remaining=%s/%s",
                job.vehicle_id,
                job.flight_id,
                service_type,
                moved_units,
                job.current_service_remaining_units,
                job.current_service_total_units,
            )

            with self.Session() as session:
                await self.dispatch_job_phase(session=session, job=job, direction="to_home")

        except asyncio.CancelledError:
            return
            

    async def handle_vehicle_returned_home(self, vehicle_id: str) -> None:
        job = self._jobs_by_vehicle_id.get(vehicle_id)
        if job is None:
            return

        with self.Session() as session:
            vehicle = session.get(models.Vehicle, vehicle_id)
            if vehicle is None:
                return

            vehicle.status = "Available"
            vehicle.flight_id = None
            vehicle.destination = None
            vehicle.route_id = None
            session.commit()

        logging.info(
            "[ground_ops] vehicle returned home vehicle_id=%s flight_id=%s service=%s remaining=%s/%s",
            vehicle_id,
            job.flight_id,
            job.service_sequence[job.current_index],
            job.current_service_remaining_units,
            job.current_service_total_units,
        )

        waiting_flight_ids = [
            fid
            for fid, queued_job in self._jobs_by_flight_id.items()
            if queued_job is not None and not queued_job.vehicle_id and fid != job.flight_id
        ]

        for waiting_flight_id in waiting_flight_ids:
            await self.retry_waiting_job_for_flight(waiting_flight_id)

        if job.current_service_remaining_units > 0:
            current_service = job.service_sequence[job.current_index]

            logging.info(
                "[ground_ops] repeating service flight_id=%s service=%s remaining=%s",
                job.flight_id,
                current_service,
                job.current_service_remaining_units,
            )

            with self.Session() as session:
                next_vehicle = self.pick_vehicle_for_service(
                    session=session,
                    stand_id=job.stand_id,
                    service_type=current_service,
                )

                if next_vehicle is None:
                    waiting_job = ActiveGroundJob(
                        flight_id=job.flight_id,
                        airplane_id=job.airplane_id,
                        stand_id=job.stand_id,
                        service_sequence=job.service_sequence,
                        current_index=job.current_index,
                        vehicle_id="",
                        direction="to_stand",
                        flow_mode=job.flow_mode,
                        current_service_total_units=job.current_service_total_units,
                        current_service_remaining_units=job.current_service_remaining_units,
                    )
                    self._jobs_by_vehicle_id.pop(job.vehicle_id, None)
                    self._service_tasks.pop(job.vehicle_id, None)
                    self._jobs_by_flight_id[job.flight_id] = waiting_job

                    logging.info(
                        "[ground_ops] queued waiting retry flight_id=%s service=%s remaining=%s",
                        job.flight_id,
                        current_service,
                        job.current_service_remaining_units,
                    )
                    return

                self._jobs_by_vehicle_id.pop(job.vehicle_id, None)
                self._service_tasks.pop(job.vehicle_id, None)

                job.vehicle_id = next_vehicle.id
                await self.dispatch_job_phase(session=session, job=job, direction="to_stand")
                return

        next_index = job.current_index + 1
        if next_index >= len(job.service_sequence):
            self._jobs_by_vehicle_id.pop(job.vehicle_id, None)
            self._jobs_by_flight_id.pop(job.flight_id, None)
            self._service_tasks.pop(job.vehicle_id, None)

            logging.info(
                "[ground_ops] all services completed flight_id=%s",
                job.flight_id,
            )
            return

        next_service = job.service_sequence[next_index]

        with self.Session() as session:
            airplane = session.get(models.Airplane, job.airplane_id)
            if airplane is None:
                return

            total_units = resolve_capacity_workload(
                airplane=airplane,
                service_type=next_service,
            )

        logging.info(
            "[ground_ops] advancing to next service flight_id=%s next_service=%s total_units=%s",
            job.flight_id,
            next_service,
            total_units,
        )

        if not service_allowed_for_stand(stand_id=job.stand_id, service_type=next_service):
            logging.warning(
                "[ground_ops] invalid chained service stand=%s flight_id=%s service=%s",
                job.stand_id,
                job.flight_id,
                next_service,
            )
            self._jobs_by_vehicle_id.pop(job.vehicle_id, None)
            self._jobs_by_flight_id.pop(job.flight_id, None)
            self._service_tasks.pop(job.vehicle_id, None)
            return

        with self.Session() as session:
            next_vehicle = self.pick_vehicle_for_service(
                session=session,
                stand_id=job.stand_id,
                service_type=next_service,
            )

            if next_vehicle is None:
                logging.info(
                    "[ground_ops] no available vehicle for next service stand=%s flight_id=%s service=%s",
                    job.stand_id,
                    job.flight_id,
                    next_service,
                )
                self._jobs_by_vehicle_id.pop(job.vehicle_id, None)
                self._service_tasks.pop(job.vehicle_id, None)

                waiting_job = ActiveGroundJob(
                    flight_id=job.flight_id,
                    airplane_id=job.airplane_id,
                    stand_id=job.stand_id,
                    service_sequence=job.service_sequence,
                    current_index=next_index,
                    vehicle_id="",
                    direction="to_stand",
                    flow_mode=job.flow_mode,
                    current_service_total_units=total_units,
                    current_service_remaining_units=total_units,
                )
                self._jobs_by_flight_id[job.flight_id] = waiting_job
                return

            self._jobs_by_vehicle_id.pop(job.vehicle_id, None)
            self._service_tasks.pop(job.vehicle_id, None)

            next_job = ActiveGroundJob(
                flight_id=job.flight_id,
                airplane_id=job.airplane_id,
                stand_id=job.stand_id,
                service_sequence=job.service_sequence,
                current_index=next_index,
                vehicle_id=next_vehicle.id,
                direction="to_stand",
                flow_mode=job.flow_mode,
                current_service_total_units=total_units,
                current_service_remaining_units=total_units,
            )

            await self.dispatch_job_phase(session=session, job=next_job, direction="to_stand")



    async def sleep_sim_seconds(self, seconds: float) -> None:
        if seconds <= 0:
            return

        if self._clock is None:
            await asyncio.sleep(seconds)
            return

        if self._clock_lock is None:
            target = self._clock.now() + timedelta(seconds=seconds)
        else:
            async with self._clock_lock:
                target = self._clock.now() + timedelta(seconds=seconds)

        while True:
            if self._clock_lock is None:
                now = self._clock.now()
                time_scale = float(getattr(self._clock, "time_scale", 1.0))
            else:
                async with self._clock_lock:
                    now = self._clock.now()
                    time_scale = float(getattr(self._clock, "time_scale", 1.0))

            remaining = (target - now).total_seconds()
            if remaining <= 0:
                return

            timeout = 1.0 if time_scale <= 0 else min(1.0, max(0.01, remaining / time_scale))

            if self._clock_changed is None or self._clock_changed.is_set():
                await asyncio.sleep(timeout)
                continue

            try:
                await asyncio.wait_for(self._clock_changed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass


    async def retry_waiting_job_for_flight(self, flight_id: str) -> None:
        job = self._jobs_by_flight_id.get(flight_id)
        if job is None or job.vehicle_id:
            return

        service_type = job.service_sequence[job.current_index]

        with self.Session() as session:
            vehicle = self.pick_vehicle_for_service(
                session=session,
                stand_id=job.stand_id,
                service_type=service_type,
            )
            if vehicle is None:
                return

            resumed = ActiveGroundJob(
                flight_id=job.flight_id,
                airplane_id=job.airplane_id,
                stand_id=job.stand_id,
                service_sequence=job.service_sequence,
                current_index=job.current_index,
                vehicle_id=vehicle.id,
                direction="to_stand",
                flow_mode=job.flow_mode,
                current_service_total_units=job.current_service_total_units,
                current_service_remaining_units=job.current_service_remaining_units,
            )

            await self.dispatch_job_phase(session=session, job=resumed, direction="to_stand")


    def vehicle_speed_profile_for_segment(
        self,
        *,
        service_type: str,
        direction: str,
        segment_name: str,
        index: int,
        total: int,
    ) -> dict:
        is_bus = service_type == "passenger_transfer"

        cruise_speed = 0.8 if is_bus else 0.5
        approach_speed = 0.2
        depart_speed = 0.2

        if "Master_O" in segment_name:
            return {
                "purpose": f"{service_type}_{direction}_master",
                "initial_speed_kmh": cruise_speed,
                "target_speed_kmh": cruise_speed,
                "acceleration_mps2": 0.15,
                "deceleration_mps2": 0.15,
            }

        if direction == "to_stand" and index == total - 1:
            return {
                "purpose": f"{service_type}_{direction}_approach",
                "initial_speed_kmh": cruise_speed,
                "target_speed_kmh": approach_speed,
                "acceleration_mps2": 0.15,
                "deceleration_mps2": 0.2,
            }

        if direction == "to_home" and index == 0:
            return {
                "purpose": f"{service_type}_{direction}_depart",
                "initial_speed_kmh": depart_speed,
                "target_speed_kmh": cruise_speed,
                "acceleration_mps2": 0.2,
                "deceleration_mps2": 0.2,
            }

        return {
            "purpose": f"{service_type}_{direction}_cruise",
            "initial_speed_kmh": cruise_speed,
            "target_speed_kmh": cruise_speed,
            "acceleration_mps2": 0.2,
            "deceleration_mps2": 0.2,
        }


    def attach_vehicle_speed_profiles(
        self,
        *,
        segments: list[dict],
        service_type: str,
        direction: str,
    ) -> list[dict]:
        enriched: list[dict] = []

        for index, segment in enumerate(segments):
            item = dict(segment)
            item["speed_profile"] = self.vehicle_speed_profile_for_segment(
                service_type=service_type,
                direction=direction,
                segment_name=str(segment.get("name", "")),
                index=index,
                total=len(segments),
            )
            enriched.append(item)

        return enriched
