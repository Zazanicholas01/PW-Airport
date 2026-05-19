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
from sqlalchemy import select

from src.db import models
from src.schedulers.flight_scheduler import FlightSlidingWindowScheduler
from src.utils.datetimes import as_rome, as_utc
from src.utils.event_log import append_event
from src.utils.geo_direction import direction_for_airport_icao
from src.utils.mapping import landing_source_for_range, range_for_airplane_model
from src.utils.landing_timing import landing_spawn_lead_seconds
from src.path_commands import make_start_path_command

from src.transport.session import SessionContext

DEPARTURE_ASSIGNMENT_RETRY_DELAY_S = 120.0


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


CITY_LABEL_OVERRIDES = {
    "LIAG": "Amaro",
    "LIML": "Milano Linate",
    "LIMC": "Milano Malpensa",
    "LIPZ": "Venezia Marco Polo",
    "LIMJ": "Genova",
    "LIRF": "Roma Fiumicino",
    "LIRN": "Napoli",
    "ZSPD": "Shanghai Pudong",
    "OMDB": "Dubai",
    "KORD": "Chicago O'Hare",
    "KJFK": "New York",
    "KLAX": "Los Angeles",
    "EGLL": "London Heathrow",
    "LFPG": "Paris Charles de Gaulle",
    "EDDF": "Frankfurt",
    "EHAM": "Amsterdam Schiphol",
    "LEMD": "Madrid Barajas",
    "LTFM": "Istanbul",
}


def _airport_label(icao: str, airport_names: dict[str, str]) -> str:
    if not icao:
        return "--"
    return CITY_LABEL_OVERRIDES.get(icao) or airport_names.get(icao) or icao


def _remote_airport_label(
    *,
    origin: str,
    destination: str,
    local_airport_icao: str,
    airport_names: dict[str, str],
) -> str:
    if origin == local_airport_icao:
        return _airport_label(destination, airport_names)
    if destination == local_airport_icao:
        return _airport_label(origin, airport_names)

    origin_label = _airport_label(origin, airport_names)
    destination_label = _airport_label(destination, airport_names)
    return f"{origin_label} -> {destination_label}"


def _airline_label(airline_code: str | None, airline_names: dict[str, str]) -> str:
    if not airline_code:
        return "--"

    airline_name = airline_names.get(airline_code)
    if airline_name:
        return f"{airline_name} ({airline_code})"

    return airline_code


def _duration_label(departure_time, arrival_time) -> str:
    if departure_time is None or arrival_time is None:
        return "--"

    departure_utc = as_utc(departure_time)
    arrival_utc = as_utc(arrival_time)

    minutes = max(0, round((arrival_utc - departure_utc).total_seconds() / 60))
    if minutes < 60:
        return f"{minutes} min"

    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours}h {remaining_minutes:02d}m"


def _scheduler_window_row(
    flight,
    *,
    airport_icao: str,
    airport_names: dict[str, str],
    airline_names: dict[str, str],
) -> dict:
    reference_time = _flight_reference_time(flight, airport_icao)

    departure_time = getattr(flight, "departure_time", None)
    arrival_time = getattr(flight, "arrival_time", None)

    origin = str(getattr(flight, "origin", "") or "")
    destination = str(getattr(flight, "destination", "") or "")
    airline_code = str(getattr(flight, "airline_code", "") or "")
    status = str(getattr(flight, "status", "") or "")
    flight_code = str(getattr(flight, "icao", None) or getattr(flight, "id", "") or "")

    direction = "arrival" if destination == airport_icao else "departure"
    departure_label = as_rome(departure_time).strftime("%H:%M") if departure_time else "--:--"
    arrival_label = as_rome(arrival_time).strftime("%H:%M") if arrival_time else "--:--"
    title_time = arrival_label if direction == "arrival" else departure_label
    title_route = _remote_airport_label(
        origin=origin,
        destination=destination,
        local_airport_icao=airport_icao,
        airport_names=airport_names,
    )

    return {
        "id": str(getattr(flight, "id", "") or ""),
        "direction": direction,
        "card_title": f"{title_route} - {title_time}",
        "departure_time": departure_label,
        "arrival_time": arrival_label,
        "delta_time": _duration_label(departure_time, arrival_time),
        "reference_unix_ms": int(reference_time.timestamp() * 1000) if reference_time else None,
        "flight_number": flight_code,
        "airline": _airline_label(airline_code, airline_names),
        "route": _remote_airport_label(
            origin=origin,
            destination=destination,
            local_airport_icao=airport_icao,
            airport_names=airport_names,
        ),
        "type": str(getattr(flight, "tipo", "") or ""),
        "status": status,
        "status_class": _status_pill_class(status),
        "airplane": str(getattr(flight, "airplane_id", None) or "--"),
    }


def _dynamic_landing_spawn_context(ctx: SessionContext, flight) -> tuple[object, dict, float] | None:
    direction = direction_for_airport_icao(getattr(flight, "origin", None))
    spawn_position = ctx.setup_bus.state.landing_spawn_position

    if direction is not None:
        spawn_position = ctx.setup_bus.state.landing_spawn_positions_by_direction.get(
            direction.value,
            spawn_position,
        )

    airport_position = ctx.setup_bus.state.airport_position
    if not isinstance(spawn_position, dict) or not isinstance(airport_position, dict):
        return None

    airplane_id = getattr(flight, "airplane_id", None)
    airplane_model = None
    if isinstance(airplane_id, str) and airplane_id:
        airplane_model = ctx.flight_actions.get_airplane_prefab(airplane_id=airplane_id)

    route_segments = None
    if isinstance(airplane_model, str) and airplane_model:
        try:
            landing_id = landing_source_for_range(range_for_airplane_model(airplane_model))
            route_segments = []
            if direction is not None:
                route_segments.append({
                    "name": f"Spline_Landing_{direction.value}",
                    "t_start": 0.0,
                    "t_end": 1.0,
                })
            route_segments.extend([
                {
                    "name": "Spline_Landing_Route",
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
                {
                    "name": "Spline_Landing_Approach",
                    "t_start": 0.0,
                    "t_end": 1.0,
                },
            ])
        except ValueError:
            route_segments = None

    def spline_lookup(name: str):
        if name == "MasterSpline":
            return getattr(ctx.graph, "master_spline", None)
        for spline in getattr(ctx.graph, "splines", []):
            if isinstance(spline, dict) and spline.get("name") == name:
                return spline
        return None

    lead_seconds = landing_spawn_lead_seconds(
        spawn_position=spawn_position,
        airport_position=airport_position,
        route_segments=route_segments,
        spline_lookup=spline_lookup,
    )

    return direction, spawn_position, lead_seconds



async def flight_scheduler_loop(
    ctx: SessionContext,
    *,
    poll_seconds: float = 30.0,
    window: timedelta = timedelta(hours=WINDOW_TIMEDELTA_HOURS),
    ) -> None:

    # Wait for setup to be completed
    while not ctx.setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)

    if ctx.initial_spawns_ready is not None:
        await ctx.initial_spawns_ready.wait()

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

    async with ctx.clock_lock:
        next_runtime_generation_at = as_utc(ctx.clock.now()) + GENERATOR_CONFIG.RUNTIME_FLIGHT_EVERY

    while True:

        # Read current time and time scale of the simulation
        async with ctx.clock_lock:
            now = as_utc(ctx.clock.now())
            time_scale = float(getattr(ctx.clock, "time_scale", 1.0))

        while now >= next_runtime_generation_at:
            generated_count = ctx.flight_actions.generate_runtime_flights(
                1,
                2,
                scheduler.window,
            )

            logging.info(
                "[flight_scheduler] runtime flights generated count=%d scheduled_at=%s now=%s",
                generated_count,
                next_runtime_generation_at.isoformat(),
                now.isoformat(),
            )

            append_event({
                "type": "backend_event",
                "event": "runtime_flights_generated",
                "count": generated_count,
                "scheduled_at": next_runtime_generation_at.isoformat(),
                "generated_at": now.isoformat(),
            })

            next_runtime_generation_at += timedelta(hours=1)

        # List flights inside scheduling window
        flights = ctx.flight_actions.list_flights_in_sliding_window(
            airport_icao=ctx.airport_icao,
            now_utc=now,
            window=scheduler.window,
        )

        airport_codes = {
            code
            for flight in flights
            for code in (getattr(flight, "origin", None), getattr(flight, "destination", None))
            if code
        }
        airline_codes = {
            code
            for flight in flights
            for code in (getattr(flight, "airline_code", None),)
            if code
        }

        with ctx.Session() as session:
            airport_names = {
                icao: name
                for icao, name in session.execute(
                    select(models.Airport.icao, models.Airport.name)
                    .where(models.Airport.icao.in_(airport_codes))
                ).all()
            } if airport_codes else {}
            airline_names = {
                icao: name
                for icao, name in session.execute(
                    select(models.Airline.icao, models.Airline.name)
                    .where(models.Airline.icao.in_(airline_codes))
                ).all()
            } if airline_codes else {}

        # Generate cached window rows
        window_rows = [
            _scheduler_window_row(
                flight,
                airport_icao=ctx.airport_icao,
                airport_names=airport_names,
                airline_names=airline_names,
            )
            for flight in flights
        ]

        window_rows.sort(
            key=lambda row: (
                999999999999 if row["reference_unix_ms"] is None else abs(int(row["reference_unix_ms"]) - int(now.timestamp() * 1000)),
                str(row["flight_number"]),
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
                    logging.info(
                        "[flight_scheduler] no compatible parked airplane flight_id=%s retry_in=%.0fs",
                        flight_id,
                        DEPARTURE_ASSIGNMENT_RETRY_DELAY_S,
                    )
                    scheduler.defer_retry(
                        flight_id=flight_id,
                        stage="dep",
                        delay_seconds=DEPARTURE_ASSIGNMENT_RETRY_DELAY_S,
                    )
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
                    scheduler.handled.discard((flight_id, "landing_dep"))
                    continue

                logging.info("[flight_scheduler] landing_dep: linked airplane_id=%s to flight_id=%s (Scheduled)", airplane_id, flight_id)
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

            landing_spawn_context = None
            if getattr(flight, "destination", None) == ctx.airport_icao:
                landing_spawn_context = _dynamic_landing_spawn_context(ctx, flight)

            # LANDING RESERVATION - dynamically timed from landing route distance/speed
            should_reserve_landing = False
            if landing_spawn_context is not None:
                _, _, lead_seconds = landing_spawn_context
                should_reserve_landing = scheduler.should_reserve_landing_stand_dynamic(
                    flight=flight,
                    now_utc=now,
                    lead_seconds=lead_seconds,
                )
            else:
                should_reserve_landing = scheduler.should_reserve_landing_stand(
                    flight=flight,
                    now_utc=now,
                )

            if should_reserve_landing:

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

                if ctx.ground_ops is not None and isinstance(airplane_id, str) and airplane_id:
                    await ctx.ground_ops.maybe_start_for_airplane(airplane_id)

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

                    cmd = make_start_path_command(
                        airplane_id=airplane_id,
                        flight_id=flight_id,
                        Session=ctx.Session,
                    )

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

            # SPAWN LANDING PLANE - dynamically timed from landing route distance/speed
            if landing_spawn_context is None:
                if getattr(flight, "destination", None) == ctx.airport_icao:
                    logging.warning(
                        "[flight_scheduler] landing_spawn: dynamic spawn context unavailable flight_id=%s",
                        flight_id,
                    )
                continue

            direction, spawn_position, lead_seconds = landing_spawn_context

            if scheduler.should_spawn_landing_plane_dynamic(flight=flight, now_utc=now, lead_seconds=lead_seconds):

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

                if not isinstance(spawn_position, dict):
                    logging.warning("[flight_scheduler] landing_spawn: spawn_position not set; cannot spawn flight_id=%s", flight_id)
                    scheduler.handled.discard((flight_id, "landing_spawn"))
                    continue

                logging.info(
                    "[landing_spawn][OUT] flight_id=%s airplane_id=%s prefab=%s direction=%s lead_seconds=%.1f pos=%s",
                    flight_id, airplane_id, prefab, getattr(direction, "value", None), lead_seconds, spawn_position,
                )

                # Send Spawn Plane command through bus to Unity
                await ctx.bus.send_command(ctx.commands.spawn_plane(
                    prefab=prefab,
                    stand_id=f"landing:{flight_id}",
                    position=spawn_position,
                    airplane_id=airplane_id,
                    flight_id=flight_id,
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
            should_start_landing = False
            if landing_spawn_context is not None:
                should_start_landing = scheduler.should_start_landing_approach_dynamic(
                    flight=flight,
                    now_utc=now,
                    lead_seconds=lead_seconds,
                )
            else:
                should_start_landing = scheduler.should_start_landing_approach(
                    flight=flight,
                    now_utc=now,
                )

            if should_start_landing:

                # Retrieve airplane ID from flight
                airplane_id = getattr(flight, "airplane_id", None)

                if not isinstance(airplane_id, str):
                    scheduler.handled.discard((flight_id, "landing_start"))
                    continue

                # Call Make start path command and send through bus to Unity
                cmd = make_start_path_command(
                    airplane_id=airplane_id,
                    flight_id=flight_id,
                    Session=ctx.Session,
                )

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
