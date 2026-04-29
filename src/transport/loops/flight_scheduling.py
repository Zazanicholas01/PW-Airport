import asyncio
import logging
import time
from datetime import timedelta

from src.domain.status_constants import (
    BUS_COMMANDS,
    GENERATOR_CONFIG,
    MIN_POLL_REAL_S,
    WINDOW_TIMEDELTA_HOURS,
    WAIT_FOR_PARKED_TIMEOUT_S
)

from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler
from src.utils.datetimes import as_utc
from src.utils.event_log import append_event
from src.path_commands import make_start_path_command

from src.transport.session import SessionContext


def _status_pill_class(status: str | None) -> str:
    normalized = str(status or "").lower()

    if normalized in {"parked"}:
        return "status-parked"
    if normalized in {"scheduled", "standreserved"}:
        return "status-scheduled"
    if normalized in {"reserved"}:
        return "status-default"
    if normalized in {"departing", "dep_ongoing", "landing", "lan_ongoing", "disembarking"}:
        return "status-landing"
    if normalized in {"completed"}:
        return "status-completed"

    return "status-default"


def _flight_reference_time(flight, airport_icao: str):
    origin = getattr(flight, "origin", None)
    destination = getattr(flight, "destination", None)

    if destination == airport_icao and getattr(flight, "arrival_time", None) is not None:
        return getattr(flight, "arrival_time", None)
    if origin == airport_icao and getattr(flight, "departure_time", None) is not None:
        return getattr(flight, "departure_time", None)
    if getattr(flight, "arrival_time", None) is not None:
        return getattr(flight, "arrival_time", None)
    return getattr(flight, "departure_time", None)


def _scheduler_window_row(flight, *, airport_icao: str) -> dict:
    reference_time = _flight_reference_time(flight, airport_icao)

    departure_time = getattr(flight, "departure_time", None)
    arrival_time = getattr(flight, "arrival_time", None)

    origin = str(getattr(flight, "origin", "") or "")
    destination = str(getattr(flight, "destination", "") or "")
    status = str(getattr(flight, "status", "") or "")
    flight_code = str(getattr(flight, "icao", None) or getattr(flight, "id", "") or "")

    direction = "arrival" if destination == airport_icao else "departure"

    return {
        "id": str(getattr(flight, "id", "") or ""),
        "direction": direction,
        "dep_time": departure_time.astimezone().strftime("%H:%M") if departure_time else "--:--",
        "arr_time": arrival_time.astimezone().strftime("%H:%M") if arrival_time else "--:--",
        "reference_unix_ms": int(reference_time.timestamp() * 1000) if reference_time else None,
        "flight": flight_code,
        "route": f"{origin} -> {destination}",
        "type": str(getattr(flight, "tipo", "") or ""),
        "status": status,
        "status_class": _status_pill_class(status),
        "airplane": str(getattr(flight, "airplane_id", None) or "--"),
    }



async def flight_scheduler_loop(
    ctx: SessionContext,
    *,
    poll_seconds: float = 30.0,
    window: timedelta = timedelta(hours=WINDOW_TIMEDELTA_HOURS),
    ) -> None:

    # Wait for setup to be completed
    while not ctx.setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)

    # Get landing spawn position from setup bus
    landing_spawn_position = ctx.setup_bus.state.landing_spawn_position
    logging.info("[spawn_scheduler] landing_spawn_position=%s", landing_spawn_position)

    # Create a Flight Scheduler instance
    scheduler = FlightSlidingWindowScheduler(
        airport_icao=ctx.airport_icao,
        window=window,
    )

    # DEBUG - Ensure first departure matches an initial parked plane

    start_wait = time.monotonic()
    while True:
        
        parked_count = ctx.flight_actions.count_parked_airplanes()
        if parked_count > 0:
            break

        # If timeout elapses, break anyway and skip debug logic
        if (time.monotonic() - start_wait) > WAIT_FOR_PARKED_TIMEOUT_S:
            logging.warning("[flight_scheduler] no parked airplanes after %.1fs; generating flights anyway", WAIT_FOR_PARKED_TIMEOUT_S)
            break
        await asyncio.sleep(0.1)

    # Create Random Flight Generator instance
    ctx.flight_actions.generate_debug_flights(
        GENERATOR_CONFIG.RANDOM_FLIGHTS_COUNT,
        ensure_in_window=GENERATOR_CONFIG.ENSURE_IN_WINDOW,
        window=scheduler.window
    )
    logging.info(f"[flight_scheduler] generated debug flights (n={GENERATOR_CONFIG.RANDOM_FLIGHTS_COUNT})")
    append_event({
        "type": "backend_event",
        "event": "debug_flights_generated",
        "count": GENERATOR_CONFIG.RANDOM_FLIGHTS_COUNT,
    })

    # Initialize timestamp used to rate-limit scheduling window logging
    last_window_log = 0.0

    while True:

        # Read current time and time scale of the simulation
        async with ctx.clock_lock:
            now = as_utc(ctx.clock.now())
            time_scale = float(getattr(ctx.clock, "time_scale", 1.0))

        # List flights inside scheduling window
        flights = ctx.flight_actions.list_flights_in_sliding_window(
            airport_icao=ctx.airport_icao,
            now_utc=now,
            window=scheduler.window,
        )

        # Generate cached window rows
        window_rows = [
            _scheduler_window_row(flight, airport_icao=ctx.airport_icao)
            for flight in flights
        ]

        window_rows.sort(
            key=lambda row: (
                999999999999 if row["reference_unix_ms"] is None else abs(int(row["reference_unix_ms"]) - int(now.timestamp() * 1000)),
                str(row["flight"]),
            )
        )

        # Stream event to JSON event log file
        append_event({
            "type": "scheduler_window",
            "airport_icao": ctx.airport_icao,
            "window_minutes": int(scheduler.window.total_seconds() // 60),
            "generated_at": now.isoformat(),
            "rows": window_rows,
        })

        # Query flights currently inside the window
        t = time.monotonic()
        if (t - last_window_log) >= poll_seconds:
            last_window_log = t

            # Build lightweight dictionaries for logging purposes
            items = [
                {
                    "id": getattr(flight, "id", None),
                    "origin": getattr(flight, "origin", None),
                    "destination": getattr(flight, "destination", None),
                    "dep": getattr(flight, "departure_time", None),
                    "arr": getattr(flight, "arrival_time", None),
                    "tipo": getattr(flight, "tipo", None),
                    "status": getattr(flight, "status", None),
                    "airplane_id": getattr(flight, "airplane_id", None),
                }
                for flight in flights
            ]

            # Log scheduling window's flights
            logging.info("[flight_scheduler] window now=%s time_scale=%.2f flights_in_window=%d flights=%s",
                now.isoformat(),
                time_scale,
                len(items),
                items
            )

        for flight in flights:

            # Get flight ID for every flight through iteration
            flight_id = getattr(flight, "id", None)
            if not isinstance(flight_id, str) or not flight_id:
                continue

            # DEPARTURE - In Window from Departure Time
            if scheduler.should_schedule_departure(flight=flight, now_utc=now):

                # Compute required type for the flight (Cargo / Passengers)
                required_type = ctx.flight_actions.normalize_flight_type(getattr(flight, "tipo", None))

                # Assign airplane to the flight with required type
                assignment = ctx.flight_actions.assign_airplane_to_departure_flight(
                    flight_id=flight_id, 
                    required_type=required_type
                )
                if assignment is None:
                    logging.info("[flight_scheduler] no compatible parked airplane flight_id=%s", flight_id)
                    scheduler.handled.discard((flight_id, "dep"))
                    continue

                # Assign a departure path to the airplane from Stand --> Departure spline
                airplane_id, stand_id = assignment
                route_id = ctx.flight_actions.assign_departure_path_for_flight(
                    flight_id=flight_id,
                    airplane_id=airplane_id,
                    stand_id=stand_id,
                )

                if route_id is None:
                    logging.warning(
                        "[flight_scheduler] departure path assignment failed airplane_id=%s stand_id=%s flight_id=%s",
                        airplane_id,
                        stand_id,
                        flight_id,
                    )
                    scheduler.handled.discard((flight_id, "dep"))
                    continue

                logging.info("[flight_scheduler] departure assigned airplane_id=%s stand_id=%s flight_id=%s", airplane_id, stand_id, flight_id)
                append_event({
                    "type": "backend_event",
                    "event": "departure_assigned",
                    "flight_id": flight_id,
                    "airplane_id": airplane_id,
                    "stand_id": stand_id,
                })
                continue

            # LANDING - In Window for Landing Flights on Departure Time
            if scheduler.should_assign_landing_plane(flight=flight, now_utc=now):
                logging.info("[flight_scheduler] landing_dep: due flight_id=%s dep=%s", flight_id, getattr(flight, "departure_time", None))

                # Create and assign airplane for landing flight that needs to depart from a remote airport
                airplane_id = ctx.flight_actions.create_and_assign_airplane_for_landing_departure(
                    flight_id=flight_id, 
                    prefab_picker=ctx.prefab_store.pick_plane_prefab
                )
                if airplane_id is None:
                    logging.info("[flight_scheduler] landing_dep: could not create/link airplane flight_id=%s", flight_id)
                    continue

                logging.info("[flight_scheduler] landing_dep: linked airplane_id=%s to flight_id=%s (Lan_Ongoing)", airplane_id, flight_id)
                append_event({
                    "type": "backend_event",
                    "event": "landing_plane_assigned",
                    "flight_id": flight_id,
                    "airplane_id": airplane_id,
                })
                continue

            # MARK LANDING DEPARTED - Marks a landing flight as departed from a remote airport
            if scheduler.should_mark_landing_departed(flight=flight, now_utc=now):
                ctx.flight_actions.mark_landing_departed(flight_id=flight_id)
                logging.info("[flight_scheduler] landing_dep: departed flight_id=%s -> Lan_Ongoing", flight_id)
                append_event({
                    "type": "backend_event",
                    "event": "landing_departed",
                    "flight_id": flight_id,
                })
                continue

            # LANDING RESERVATION - In Window on Arrival Time for Landing 
            if scheduler.should_reserve_landing_stand(flight=flight, now_utc=now):

                result = ctx.flight_actions.assign_arrival_route_or_parking(flight_id=flight_id)

                if result is None:
                    logging.warning("[flight_scheduler] landing_arr: route decision failed flight_id=%s", flight_id)
                    scheduler.handled.discard((flight_id, "landing_arr"))
                    continue

                airplane_id = getattr(flight, "airplane_id", None)
                decision = result.get("decision")

                # STAND AVAILABLE DIRECT LANDING
                if decision == "land":
                    logging.info(
                        "[flight_scheduler] landing_arr: direct landing stand_id=%s route_id=%s flight_id=%s",
                        result.get("stand_id"),
                        result.get("route_id"),
                        flight_id,
                    )

                    append_event({
                        "type": "backend_event",
                        "event": "landing_stand_reserved",
                        "flight_id": flight_id,
                        "stand_id": result.get("stand_id"),
                        "airplane_id": airplane_id,
                        "route_id": result.get("route_id"),
                    })
                    continue

                # STAND UNAVAILABLE - PARKING LANDING
                if decision == "parking":
                    logging.info(
                        "[flight_scheduler] landing_arr: routed to parking parking_n=%s route_id=%s flight_id=%s",
                        result.get("parking_n"),
                        result.get("route_id"),
                        flight_id,
                    )

                    append_event({
                        "type": "backend_event",
                        "event": "landing_parking_reserved",
                        "flight_id": flight_id,
                        "parking_n": result.get("parking_n"),
                        "airplane_id": airplane_id,
                        "route_id": result.get("route_id"),
                    })
                    continue

                # PARKING UNAVAILABLE - DELAY 15 MINUTES
                if decision == "delayed":
                    logging.info(
                        "[flight_scheduler] landing_arr: no stand or parking; delayed arrival 15 minutes flight_id=%s",
                        flight_id,
                    )

                    append_event({
                        "type": "backend_event",
                        "event": "landing_arrival_delayed",
                        "flight_id": flight_id,
                        "minutes": 15,
                    })

                    scheduler.handled.discard((flight_id, "landing_arr"))
                    continue


            # START DEPARTURE EMBARKING - 5 minutes before departure time
            if scheduler.should_start_departure_embarking(flight=flight, now_utc=now):

                # Retrieve airplane ID from the flight
                airplane_id = getattr(flight, "airplane_id", None)

                # Execute flight action
                ctx.flight_actions.mark_departure_embarking(flight_id=flight_id)

                logging.info(
                    "[flight_scheduler] departure embarking flight_id=%s airplane_id=%s",
                    flight_id,
                    airplane_id,
                )

                # Stream event to dashboard
                append_event({
                    "type": "backend_event",
                    "event": "departure_embarking_started",
                    "flight_id": flight_id,
                    "airplane_id": airplane_id,
                })
                continue


            # START DEPARTURE MOVEMENT - Departure Time > Now
            if scheduler.should_start_departure_movement(flight=flight, now_utc=now):

                # Retrieve airplane ID from flight
                airplane_id = getattr(flight, "airplane_id", None)

                # Make start path command for the airplane and send through bus to Unity
                if isinstance(airplane_id, str):

                    cmd = make_start_path_command(airplane_id=airplane_id, Session=ctx.Session)

                    if cmd is None:
                        logging.warning("[start_path][SKIP] flight_id=%s airplane_id=%s (no route/segments)", flight_id, airplane_id)
                        scheduler.handled.discard((flight_id, "dep_start"))
                        continue
                    else:
                        ctx.flight_actions.mark_departure_started(flight_id=flight_id)
                        logging.info("[start_path][OUT] flight_id=%s airplane_id=%s route_id=%s segments=%d now=%s",
                            flight_id, 
                            cmd["airplane_id"], 
                            cmd["route_id"], 
                            len(cmd["segments"]), 
                            now.isoformat()
                        )
                        
                        await ctx.bus.send_command(cmd)
                        logging.info("[flight_scheduler] start_path departure airplane_id=%s flight_id=%s", airplane_id, flight_id)
                        append_event({
                            "type": "backend_event",
                            "event": "departure_started",
                            "flight_id": flight_id,
                            "airplane_id": airplane_id,
                            "route_id": cmd["route_id"],
                        })
                continue

            # SPAWN LANDING PLANE - 1 Minute Before Arrival Time
            if scheduler.should_spawn_landing_plane(flight=flight, now_utc=now):

                # Retrieve airplane ID from flight
                airplane_id = getattr(flight, "airplane_id", None)
                if not isinstance(airplane_id, str) or not airplane_id:
                    scheduler.handled.discard((flight_id, "landing_spawn"))
                    continue

                # Retrieve prefab name from airplane
                prefab = ctx.flight_actions.get_airplane_prefab(airplane_id=airplane_id)

                # Sanity checks on prefab and landing spawn position
                if not isinstance(prefab, str) or not prefab:
                    logging.warning("[flight_scheduler] Landing spawn: missing prefab airplane_id=%s flight_id=%s", airplane_id, flight_id)
                    scheduler.handled.discard((flight_id, "landing_spawn"))
                    continue

                if not isinstance(landing_spawn_position, dict):
                    logging.warning("[flight_scheduler] landing_spawn: landing_spawn_position not set; cannot spawn flight_id=%s", flight_id)
                    scheduler.handled.discard((flight_id, "landing_spawn"))
                    continue

                logging.info(
                    "[landing_spawn][OUT] flight_id=%s airplane_id=%s prefab=%s pos=%s",
                    flight_id, airplane_id, prefab, landing_spawn_position,
                )

                # Send Spawn Plane command through bus to Unity
                await ctx.bus.send_command(ctx.commands.spawn_plane(
                    prefab=prefab,
                    stand_id=f"landing:{flight_id}",
                    position=landing_spawn_position,
                    airplane_id=airplane_id,
                    spawn_context="landing",
                ))
                logging.info("[flight_scheduler] landing_spawn: spawned airplane_id=%s flight_id=%s", airplane_id, flight_id)
                append_event({
                    "type": "backend_event",
                    "event": "landing_spawn",
                    "flight_id": flight_id,
                    "airplane_id": airplane_id,
                    "prefab": prefab,
                })

            # START LANDING MOVEMENT
            if scheduler.should_start_landing_approach(flight=flight, now_utc=now):

                # Retrieve airplane ID from flight
                airplane_id = getattr(flight, "airplane_id", None)

                if not isinstance(airplane_id, str):
                    scheduler.handled.discard((flight_id, "landing_start"))
                    continue

                # Call Make start path command and send through bus to Unity
                cmd = make_start_path_command(airplane_id=airplane_id, Session=ctx.Session)

                if cmd is None:
                    logging.warning(
                        "[start_path][SKIP] landing flight_id=%s airplane_id=%s reason=no route/segments",
                        flight_id,
                        airplane_id,
                    )
                    scheduler.handled.discard((flight_id, "landing_start"))
                    continue

                # Send start path command
                await ctx.bus.send_command(cmd)

                # Log to dashboard web
                append_event({
                    "type": "backend_event",
                    "event": "landing_approach_started",
                    "flight_id": flight_id,
                    "airplane_id": airplane_id,
                    "route_id": cmd["route_id"],
                })

        # Convert simulation polling to real time sleep based on time_scale
        poll_real_s = max(MIN_POLL_REAL_S, poll_seconds / max(time_scale, 1.0))

        # Check for wake event (Change of time scale from Unity UI)
        try:
            await asyncio.wait_for(ctx.clock_changed.wait(), timeout=poll_real_s)
            ctx.clock_changed.clear()
        except asyncio.TimeoutError:
            pass
