from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone

from src.domain.status_constants import BUS_COMMANDS, CLOCK_HERTZ, EVT_EVERY_S, LOG_EVERY_S
from src.utils.datetimes import isoformat_utc_plus1
from src.utils.event_log import append_event

from src.transport.session import SessionContext
from src.transport.command_builders import build_clock_sync


def _clock_event(sync) -> dict:
    return {
        "type": "clock",
        "sim_unix_ms": sync.sim_unix_ms,
        "time_scale": sync.time_scale,
        "sync_id": sync.sync_id,
    }


async def _publish_clock_snapshot(ctx: SessionContext, sync) -> None:
    event = _clock_event(sync)
    append_event(event)

async def handle_clock_control(ctx: SessionContext, payload: dict) -> bool:

    # Get payload and sanity checks
    cmd = payload.get("command")
    if not isinstance(cmd, str):
        return False
    cmd = cmd.strip().lower()

    # Handle case of Set Time Scale command
    if cmd == BUS_COMMANDS.SET_TIME_SCALE:

        # Read requested time scale to apply and request ID
        raw = payload.get("time_scale")
        req_id = payload.get("request_id")

        # Capture before state for logging purposes
        before_scale = ctx.clock.time_scale
        before_now = ctx.clock.now().astimezone(timezone.utc)

        logging.info("[clock][IN] set_time_scale requested=%r request_id=%r before_scale=%.3f before_now=%s",
            payload.get("time_scale"),
            req_id,
            before_scale,
            isoformat_utc_plus1(before_now, timespec="seconds"),
        )

        # Convert scale to floating point and sanity checks
        try:
            scale = float(raw)
        except (TypeError, ValueError):
            return True
        
        if not math.isfinite(scale) or scale < 0.0:
            return True
        
        # Apply new time scale and build clock sync snapshot
        async with ctx.clock_lock:
            ctx.clock.set_time_scale(scale)
            sync = ctx.clock.make_sync()
        
        # Set clock changed wake event
        ctx.clock_changed.set()

        # Capture after states for logging purposes
        after_now = ctx.clock.now().astimezone(timezone.utc)

        logging.info(
            "[clock][APPLIED] set_time_scale applied=%.3f request_id=%r after_scale=%.3f after_now=%s",
            scale,
            req_id,
            ctx.clock.time_scale,
            isoformat_utc_plus1(after_now, timespec="seconds"),
        )
        
        # Send Clock Sync command to Unity
        await ctx.bus.send_command(
            ctx.commands.clock_sync(
                sync_id=sync.sync_id,
                sim_unix_ms=sync.sim_unix_ms,
                time_scale=sync.time_scale
            )
        )
        await _publish_clock_snapshot(ctx, sync)
        return True

    # Handle Set Sim Time command
    if cmd == BUS_COMMANDS.SET_SIM_TIME:

        # Get sim unix ms from payload
        raw_ms = payload.get("sim_unix_ms")
        try:
            sim_unix_ms = int(raw_ms)
        except (TypeError, ValueError):
            return True
        
        # Convert ms --> UTC datetime and set the new clock time
        new_sim = datetime.fromtimestamp(sim_unix_ms / 1000.0, tz=timezone.utc)
        
        async with ctx.clock_lock:
            ctx.clock.set_sim_time(new_sim)
            sync = ctx.clock.make_sync()
        
        ctx.clock_changed.set()
        await ctx.bus.send_command(
            ctx.commands.clock_sync(
                sync_id=sync.sync_id,
                sim_unix_ms=sync.sim_unix_ms,
                time_scale=sync.time_scale,
            )
        )
        await _publish_clock_snapshot(ctx, sync)
        return True
    
    return False


async def clock_sync_loop(ctx: SessionContext) -> None:
    
    # Compute sync period (10 Hz)
    period = 1.0 / CLOCK_HERTZ
    logging.info("Clock sync loop started: hz=%.1f", CLOCK_HERTZ)

    # Initialize timestamps to rate-limit logs on Terminal and events on Web UI
    last_log_t = 0.0
    last_evt_t = 0.0

    while True:
        try:

            # Build clock sync snapshot and current simulation time
            async with ctx.clock_lock:
                sync = ctx.clock.make_sync()
                sim_now = ctx.clock.now()

            # Send Clock Sync command to Unity
            await ctx.bus.send_command(
                ctx.commands.clock_sync(
                    sync_id=sync.sync_id,
                    sim_unix_ms=sync.sim_unix_ms,
                    time_scale=sync.time_scale,
                )
            )

            t = time.monotonic()

            # Clock Sync Logging in the CLI
            if (t - last_log_t) >= LOG_EVERY_S:
                last_log_t = t
                logging.info(
                    "[clock_sync] sim_now=%s sim_unix_ms=%d time_scale=%.2f sync_id=%d",
                    isoformat_utc_plus1(sim_now, timespec="seconds"),
                    sync.sim_unix_ms,
                    sync.time_scale,
                    sync.sync_id,
                )

            # Event Sync Logging in the Web UI
            if (t - last_evt_t) >= EVT_EVERY_S:
                last_evt_t = t
                await _publish_clock_snapshot(ctx, sync)

                # logging.info(
                #     "[clock_sync][PY->WEB] sim_unix_ms=%d time_scale=%.2f sync_id=%d",
                #     sync.sim_unix_ms,
                #     sync.time_scale,
                #     sync.sync_id,
                # )

            await asyncio.sleep(period)

        except asyncio.CancelledError:
            logging.info("[clock_sync] Loop cancelled")
            raise
        
        except Exception:
            logging.exception("[clock_sync] Loop crashed")
            await asyncio.sleep(1.0)
