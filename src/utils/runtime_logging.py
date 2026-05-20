from __future__ import annotations

import logging
import time
from typing import Any

from src.domain.status_constants import LOGGERS
from src.utils.event_log import append_event

runtime_logger = logging.getLogger(LOGGERS.RUNTIME)
_summary_state: dict[str, tuple[float, tuple[tuple[str, str], ...]]] = {}


def _clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


def _fingerprint(fields: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, str(value)) for key, value in fields.items()))


def runtime_log(event: str, message: str, **fields: Any) -> None:
    payload = {
        "event": event,
        **_clean_fields(fields),
    }

    runtime_logger.info(message)
    try:
        append_event({"type": "runtime_log", "message": message, "fields": payload}, filename="runtime.jsonl")
    except Exception:
        runtime_logger.debug("Failed to append runtime JSONL event", exc_info=True)


def runtime_summary(
    event: str,
    message: str,
    *,
    aggregate_key: str | None = None,
    min_interval_seconds: float = 0.0,
    **fields: Any,
) -> None:
    payload = {"event": event, **_clean_fields(fields)}
    key = aggregate_key or event
    now = time.monotonic()
    fingerprint = _fingerprint(payload)

    previous = _summary_state.get(key)
    if previous is not None:
        last_seen, last_fingerprint = previous
        if fingerprint == last_fingerprint and (now - last_seen) < min_interval_seconds:
            return

    _summary_state[key] = (now, fingerprint)
    runtime_logger.info(message)
    try:
        append_event({"type": "runtime_summary", "message": message, "fields": payload}, filename="runtime.jsonl")
    except Exception:
        runtime_logger.debug("Failed to append runtime summary event", exc_info=True)
