from __future__ import annotations

import asyncio
import logging

from src.schedulers.spawn_scheduler import SpawnScheduler
from src.utils.event_log import append_event

from src.transport.session import SessionContext
from src.transport.command_builders import build_spawn_plane

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
    
    # Initialize Spawn Scheduler instance and build initial spawn commands
    scheduler = SpawnScheduler(prefab_store=ctx.prefab_store, commands=ctx.commands, session_factory=ctx.Session)
    commands = scheduler.plan_initial_spawns()
    if not commands:
        logging.info("No initial spawns commands generated")
        return

    # Send commands through bus to Unity
    for cmd in commands:
        await ctx.bus.send_command(cmd)

    logging.info("Scheduled %d initial spawn commands", len(commands))
