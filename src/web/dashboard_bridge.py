from __future__ import annotations

import asyncio
import json
import logging

import websockets

logger = logging.getLogger(__name__)


async def run_dashboard_event_bridge(*, projection, observer_url: str) -> None:
    failure_count = 0
    while True:
        try:
            projection.set_bridge_status("connecting")
            logger.info("[dashboard_bridge] connecting observer=%s", observer_url)
            async with websockets.connect(observer_url, open_timeout=5) as ws:
                failure_count = 0
                projection.set_bridge_status("connected")
                logger.info("[dashboard_bridge] connected observer=%s", observer_url)
                async for message in ws:
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(payload, dict):
                        continue

                    payload_type = str(payload.get("type") or "")
                    if payload_type == "clock":
                        projection.update_clock(payload)
                        continue

                    projection.append_log(payload)
                    dirty = projection.mark_dirty(payload)
                    if dirty:
                        await projection.schedule_recompute()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure_count += 1
            projection.set_bridge_status("disconnected")
            level = logging.WARNING if failure_count <= 3 or failure_count % 10 == 0 else logging.DEBUG
            logger.log(
                level,
                "[dashboard_bridge] observer_unavailable observer=%s failures=%s error=%s",
                observer_url,
                failure_count,
                exc,
            )
            await asyncio.sleep(2)
