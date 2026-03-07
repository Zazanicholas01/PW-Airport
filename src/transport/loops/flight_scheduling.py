import asyncio
import logging
import time
from datetime import timedelta

from src.domain.status_constants import (
    BUS_COMMANDS,
    ENSURE_IN_WINDOW,
    MIN_POLL_REAL_S,
    RANDOM_FLIGHTS_COUNT,
    WINDOW_TIMEDELTA_HOURS,
    WAIT_FOR_PARKED_TIMEOUT_S
)

from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler
from src.utils.datetimes import as_utc
from src.path_commands import make_start_path_command

from src.transport.session import SessionContext
from src.transport.command_builders import build_spawn_plane

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
    ctx.flight_actions.generate_debug_flights(RANDOM_FLIGHTS_COUNT, ensure_in_window=ENSURE_IN_WINDOW, window=scheduler.window)
    logging.info(f"[flight_scheduler] generated debug flights (n={RANDOM_FLIGHTS_COUNT})")

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
                    continue

                # Assign a departure path to the airplane from Stand --> Departure spline
                airplane_id, stand_id = assignment
                ctx.flight_actions.assign_path_to_airplane(
                    airplane_id=airplane_id,
                    source=stand_id,
                    destination="Departure",
                )

                logging.info("[flight_scheduler] departure assigned airplane_id=%s stand_id=%s flight_id=%s", airplane_id, stand_id, flight_id)
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

                logging.info("[flight_scheduler] landing_dep: linked airplane_id=%s to flight_id=%s (Ongoing)", airplane_id, flight_id)
                continue

            # MARK LANDING DEPARTED - Marks a landing flight as departed from a remote airport
            if scheduler.should_mark_landing_departed(flight=flight, now_utc=now):
                ctx.flight_actions.mark_landing_departed(flight_id=flight_id)
                logging.info("[flight_scheduler] landing_dep: departed flight_id=%s -> Ongoing", flight_id)
                continue

            # LANDING RESERVATION - In Window on Arrival Time for Landing 
            if scheduler.should_reserve_landing_stand(flight=flight, now_utc=now):

                # Retrieve stand ID that should be reserbed to a landing flight incoming
                stand_id = ctx.flight_actions.reserve_stand_and_link_airplane_for_landing_arrival(flight_id=flight_id)
                if stand_id is None:
                    logging.warning("[flight_scheduler] landing_arr: no available stands flight_id=%s", flight_id)
                    continue

                # Retrieve airplane ID from flight and assign landing path from Landing spline --> Stand
                airplane_id = getattr(flight, "airplane_id", None)
                if isinstance(airplane_id, str):
                    ctx.flight_actions.assign_landing_path_for_airplane(
                        airplane_id=airplane_id,
                        stand_id=stand_id,
                    )

                logging.info("[flight_scheduler] landing_arr: stand_id=%s reserved + plane linked flight_id=%s", stand_id, flight_id)
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
                continue

            # SPAWN LANDING PLANE - 1 Minute Before Arrival Time
            if scheduler.should_spawn_landing_plane(flight=flight, now_utc=now):

                # Retrieve airplane ID from flight
                airplane_id = getattr(flight, "airplane_id", None)
                if not isinstance(airplane_id, str) or not airplane_id:
                    continue

                # Retrieve prefab name from airplane
                prefab = ctx.flight_actions.get_airplane_prefab(airplane_id=airplane_id)

                # Sanity checks on prefab and landing spawn position
                if not isinstance(prefab, str) or not prefab:
                    logging.warning("[flight_scheduler] Landing spawn: missing prefab airplane_id=%s flight_id=%s", airplane_id, flight_id)
                elif not isinstance(landing_spawn_position, dict):
                    logging.warning("[flight_scheduler] landing_spawn: landing_spawn_position not set; cannot spawn flight_id=%s", flight_id)
                else:
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

            # START LANDING MOVEMENT
            if scheduler.should_start_landing_approach(flight=flight, now_utc=now):

                # Retrieve airplane ID from flight
                airplane_id = getattr(flight, "airplane_id", None)

                # Call Make start path command and send through bus to Unity
                if isinstance(airplane_id, str):
                    cmd = make_start_path_command(airplane_id=airplane_id, Session=ctx.Session)
                    if cmd is not None:
                        await ctx.bus.send_command(cmd)

        # Convert simulation polling to real time sleep based on time_scale
        poll_real_s = max(MIN_POLL_REAL_S, poll_seconds / max(time_scale, 1.0))

        # Check for wake event (Change of time scale from Unity UI)
        try:
            await asyncio.wait_for(ctx.clock_changed.wait(), timeout=poll_real_s)
            ctx.clock_changed.clear()
        except asyncio.TimeoutError:
            pass
