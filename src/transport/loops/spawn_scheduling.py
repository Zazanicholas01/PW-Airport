from __future__ import annotations

import asyncio
import logging

from src.schedulers.spawn_scheduler import SpawnScheduler
from src.domain.status_constants import BACKEND_EVENTS, LOG_EVENTS, MESSAGE_TYPES
from src.utils.event_log import append_event
from src.utils.runtime_logging import runtime_log

from src.transport.session import SessionContext

async def schedule_initial_spawns(ctx: SessionContext) -> None:
    
    """Attende fine setup, poi pianifica e invia i primi spawn verso Unity"""

    # Wait for setup to be finished
    while not ctx.setup_bus.state.setup_completed:
        await asyncio.sleep(0.1)

    # Append logging event for simulation start
    append_event({
        "type": "simulation_start",
        "message": "hello",
    })
    
    # Initialize Spawn Scheduler instance
    scheduler = SpawnScheduler(
        prefab_store=ctx.prefab_store, 
        commands=ctx.commands, 
        session_factory=ctx.Session
    )

    try:
        # Build initial spawn commands with helper function
        commands = scheduler.plan_initial_spawns()
        if not commands:
            logging.info("No initial spawns commands generated")
            return

        # Send commands through bus to Unity
        for cmd in commands:
            await ctx.bus.send_command(cmd)

        logging.info("Scheduled %d initial spawn commands", len(commands))
        runtime_log(
            LOG_EVENTS.PLANE_SPAWNED,
            "Initial plane spawns scheduled",
            count=len(commands),
        )
        append_event({
            "type": MESSAGE_TYPES.BACKEND_EVENT,
            "event": BACKEND_EVENTS.INITIAL_SPAWNS_SCHEDULED,
            "count": len(commands),
        })
    finally:
        if ctx.initial_spawns_ready is not None:
            ctx.initial_spawns_ready.set()
