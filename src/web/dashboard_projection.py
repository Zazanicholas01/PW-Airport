from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from src.db import models
from src.db.db_functions import list_flights_in_sliding_window
from src.domain.status_constants import FLIGHT_STATUS

logger = logging.getLogger(__name__)


@dataclass
class DashboardClockState:
    sim_unix_ms: int | None = None
    time_scale: float | None = None
    observed_at: datetime | None = None
    bridge_status: str = "connecting"
    revision: int = 0
    time_scale_revision: int = 0

    def update_from_message(self, payload: dict[str, Any]) -> None:
        raw_now_ms = payload.get("sim_unix_ms")
        raw_time_scale = payload.get("time_scale")

        try:
            sim_unix_ms = int(raw_now_ms)
        except (TypeError, ValueError):
            sim_unix_ms = None

        try:
            time_scale = float(raw_time_scale)
        except (TypeError, ValueError):
            time_scale = None

        previous_scale = self.time_scale
        changed = False
        if sim_unix_ms is not None:
            self.sim_unix_ms = sim_unix_ms
            changed = True
        if time_scale is not None:
            self.time_scale = time_scale
            if previous_scale is None or abs(previous_scale - time_scale) > 1e-9:
                self.time_scale_revision += 1
                changed = True
        if changed:
            self.revision += 1
            self.observed_at = datetime.now(timezone.utc)

    def now(self) -> datetime | None:
        if self.sim_unix_ms is None:
            return None
        anchor = datetime.fromtimestamp(self.sim_unix_ms / 1000.0, tz=timezone.utc)
        observed_at = self.observed_at
        time_scale = self.time_scale
        if observed_at is None or time_scale is None:
            return anchor

        elapsed_real_s = max(0.0, (datetime.now(timezone.utc) - observed_at).total_seconds())
        return anchor + timedelta(seconds=elapsed_real_s * time_scale)

    def snapshot_event(self) -> dict[str, Any] | None:
        now = self.now()
        if now is None:
            return None
        return {
            "type": "clock",
            "sim_unix_ms": int(now.timestamp() * 1000),
            "time_scale": self.time_scale,
            "revision": self.revision,
            "time_scale_revision": self.time_scale_revision,
            "bridge_status": self.bridge_status,
        }


@dataclass
class SnapshotCacheEntry:
    snapshot: dict[str, Any] | None = None
    dirty: bool = True
    updated_at: datetime | None = None


@dataclass
class DashboardProjectionService:
    session_factory: Callable[[], OrmSession]
    events_file: Path
    cache_ttl_seconds: float = 5.0
    recompute_debounce_seconds: float = 0.35
    max_logs: int = 200
    clock: DashboardClockState = field(default_factory=DashboardClockState)

    def __post_init__(self) -> None:
        self._snapshot_cache: dict[tuple[str, int], SnapshotCacheEntry] = {}
        self._recent_logs: deque[dict[str, Any]] = deque(maxlen=self.max_logs)
        self._lock = asyncio.Lock()
        self._recompute_task: asyncio.Task | None = None

    def load_clock_from_events_file(self) -> None:
        if not self.events_file.exists():
            return
        try:
            lines = self.events_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            logger.exception("[dashboard_projection] events file read failed path=%s", self.events_file)
            return

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("type") == "clock":
                self.clock.update_from_message(payload)
                return

    def load_recent_logs_from_events_file(self, limit: int = 100) -> None:
        if not self.events_file.exists():
            return
        try:
            lines = self.events_file.read_text(encoding="utf-8").splitlines()[-max(0, int(limit)) :]
        except Exception:
            logger.exception("[dashboard_projection] recent logs read failed path=%s", self.events_file)
            return

        self._recent_logs.clear()
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("type") != "clock":
                self._recent_logs.append(payload)

    def ensure_clock_fresh(self, max_age_seconds: float = 2.0) -> None:
        observed_at = self.clock.observed_at
        if observed_at is None:
            self.load_clock_from_events_file()
            return
        if self.clock.bridge_status == "connected":
            return
        age = (datetime.now(timezone.utc) - observed_at).total_seconds()
        if age > max_age_seconds:
            self.load_clock_from_events_file()

    def set_bridge_status(self, status: str) -> None:
        self.clock.bridge_status = status

    def update_clock(self, payload: dict[str, Any]) -> None:
        self.clock.update_from_message(payload)

    def current_clock_payload(self) -> dict[str, Any]:
        return current_clock_payload(clock_state=self.clock, events_file=self.events_file)

    def append_log(self, payload: dict[str, Any]) -> None:
        self._recent_logs.append(payload)

    def get_recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        items = list(self._recent_logs)
        return items[-max(0, int(limit)) :]

    def track_view(self, airport: str, window_minutes: int) -> None:
        key = (airport, window_minutes)
        self._snapshot_cache.setdefault(key, SnapshotCacheEntry())

    def mark_dirty(self, payload: dict[str, Any] | None = None) -> bool:
        dirty_all = True
        if isinstance(payload, dict):
            payload_type = str(payload.get("type") or "")
            event_name = str(payload.get("event") or "")
            if payload_type == "log" and not event_name:
                dirty_all = False

        if dirty_all:
            for entry in self._snapshot_cache.values():
                entry.dirty = True
        return dirty_all

    async def schedule_recompute(
        self,
        *,
        on_snapshots_updated: Callable[[], Any] | None = None,
    ) -> None:
        if self._recompute_task is not None and not self._recompute_task.done():
            return

        async def runner() -> None:
            try:
                await asyncio.sleep(self.recompute_debounce_seconds)
                await self.recompute_dirty_snapshots()
                if on_snapshots_updated is not None:
                    result = on_snapshots_updated()
                    if asyncio.iscoroutine(result):
                        await result
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[dashboard_projection] recompute_failed")
            finally:
                self._recompute_task = None

        self._recompute_task = asyncio.create_task(runner())

    async def recompute_dirty_snapshots(self) -> None:
        async with self._lock:
            for key, entry in self._snapshot_cache.items():
                if not entry.dirty:
                    continue
                snapshot = self._build_snapshot(airport=key[0], window_minutes=key[1])
                if snapshot is not None:
                    entry.snapshot = snapshot
                    entry.updated_at = datetime.now(timezone.utc)
                    entry.dirty = False

    async def get_snapshot(self, *, airport: str, window_minutes: int) -> dict[str, Any]:
        self.track_view(airport, window_minutes)
        key = (airport, window_minutes)
        entry = self._snapshot_cache[key]
        max_age = timedelta(seconds=self.cache_ttl_seconds)
        now = datetime.now(timezone.utc)
        snapshot_is_stale = entry.updated_at is None or (now - entry.updated_at) > max_age
        if entry.snapshot is None or entry.dirty or snapshot_is_stale:
            async with self._lock:
                entry = self._snapshot_cache[key]
                snapshot_is_stale = entry.updated_at is None or (now - entry.updated_at) > max_age
                if entry.snapshot is None or entry.dirty or snapshot_is_stale:
                    snapshot = self._build_snapshot(airport=airport, window_minutes=window_minutes)
                    if snapshot is not None:
                        entry.snapshot = snapshot
                        entry.updated_at = datetime.now(timezone.utc)
                        entry.dirty = False
        if entry.snapshot is None:
            raise RuntimeError("dashboard snapshot unavailable")
        return entry.snapshot

    def _build_snapshot(self, *, airport: str, window_minutes: int) -> dict[str, Any] | None:
        try:
            return build_dashboard_snapshot(
                session_factory=self.session_factory,
                clock_state=self.clock,
                events_file=self.events_file,
                airport=airport,
                window_minutes=window_minutes,
            )
        except Exception:
            logger.exception(
                "[dashboard_projection] snapshot_build_failed airport=%s window_minutes=%s",
                airport,
                window_minutes,
            )
            return self._snapshot_cache.get((airport, window_minutes), SnapshotCacheEntry()).snapshot


def build_dashboard_snapshot(
    *,
    session_factory: Callable[[], OrmSession],
    clock_state: DashboardClockState,
    events_file: Path,
    airport: str,
    window_minutes: int,
) -> dict[str, Any]:
    now_payload = current_clock_payload(clock_state=clock_state, events_file=events_file)
    now = now_payload["now"]

    flights = list_flights_in_sliding_window(
        airport_icao=airport,
        now_utc=now,
        window=timedelta(minutes=window_minutes),
    )

    def sort_key(f: Any):
        dep = getattr(f, "departure_time", None)
        arr = getattr(f, "arrival_time", None)
        t = dep or arr
        if isinstance(t, datetime) and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t or datetime.max.replace(tzinfo=timezone.utc)

    flights = sorted(flights, key=sort_key)
    flight_items = [_flight_to_dict(flight) for flight in flights]

    with session_factory() as session:
        planes = list(session.scalars(select(models.Airplane)).all())
        stands = list(session.scalars(select(models.Stand)).all())
        paths = list(session.scalars(select(models.Path)).all())

    stand_by_plane = {
        stand.airplane_id: stand
        for stand in stands
        if isinstance(getattr(stand, "airplane_id", None), str) and stand.airplane_id
    }
    path_by_id = {
        path.id: path
        for path in paths
        if isinstance(getattr(path, "id", None), int)
    }

    flights_by_plane: dict[str, list[dict[str, Any]]] = {}
    enriched_flights: list[dict[str, Any]] = []
    window_start = now
    window_end = now + timedelta(minutes=window_minutes)
    total_window_seconds = max(1.0, (window_end - window_start).total_seconds())

    for flight in flight_items:
        ref_time, ref_label = _flight_reference_time(flight, airport)
        timeline_position_pct = None
        if ref_time is not None:
            clamped_ref = min(max(ref_time, window_start), window_end)
            timeline_position_pct = round(
                ((clamped_ref - window_start).total_seconds() / total_window_seconds) * 100.0,
                3,
            )

        airplane_id = flight.get("airplane_id")
        if isinstance(airplane_id, str) and airplane_id:
            flights_by_plane.setdefault(airplane_id, []).append(flight)

        enriched_flights.append(
            {
                **flight,
                "reference_time": ref_time.isoformat() if ref_time else None,
                "reference_label": ref_label,
                "timeline_position_pct": timeline_position_pct,
            }
        )

    planes_payload: list[dict[str, Any]] = []
    for plane in planes:
        pid = getattr(plane, "id", None)
        stand = stand_by_plane.get(pid) if isinstance(pid, str) else None
        route_id = getattr(plane, "route_id", None)
        path = path_by_id.get(route_id) if isinstance(route_id, int) else None
        assigned = flights_by_plane.get(pid, [])
        primary = assigned[0] if assigned else None
        route = None
        if getattr(path, "source", None) and getattr(path, "destination", None):
            route = f"{path.source} -> {path.destination}"
        allocation_mode = "grounded" if stand is not None else ("remote" if primary is not None else "idle")

        planes_payload.append(
            {
                "id": pid,
                "status": getattr(plane, "status", None),
                "type": getattr(plane, "type", None),
                "range": getattr(plane, "range", None),
                "model": getattr(plane, "model", None),
                "speed": getattr(plane, "speed", None),
                "position": getattr(stand, "position", None),
                "stand_id": getattr(stand, "id", None),
                "stand_status": getattr(stand, "status", None),
                "route_id": route_id,
                "route_source": getattr(path, "source", None),
                "route_destination": getattr(path, "destination", None),
                "route_label": route,
                "allocated_flights": assigned,
                "active_flight_id": (primary or {}).get("icao") or (primary or {}).get("id"),
                "allocation_mode": allocation_mode,
            }
        )

    planes_payload.sort(
        key=lambda item: (
            0 if item.get("active_flight_id") else 1,
            0 if item.get("allocation_mode") == "grounded" else 1,
            str(item.get("id") or ""),
        )
    )
    active_flights = [flight for flight in enriched_flights if flight.get("status") != FLIGHT_STATUS.COMPLETED]
    allocated_planes = [plane for plane in planes_payload if plane.get("active_flight_id")]

    return {
        "clock": now_payload["clock"],
        "window": {
            "airport": airport,
            "window_minutes": window_minutes,
            "count": len(enriched_flights),
            "active_count": len(active_flights),
            "allocated_planes_count": len(allocated_planes),
            "timeline_start_iso": window_start.isoformat(),
            "timeline_end_iso": window_end.isoformat(),
            "timeline_markers": _build_timeline_markers(now=window_start, window_minutes=window_minutes),
        },
        "flights": enriched_flights,
        "planes": planes_payload,
    }


def current_clock_payload(*, clock_state: DashboardClockState, events_file: Path) -> dict[str, Any]:
    ensure_clock_fresh(clock_state=clock_state, events_file=events_file)
    cached_now = clock_state.now()
    if cached_now is not None:
        now = cached_now
        now_source = "observer"
    else:
        now = datetime.now(timezone.utc)
        now_source = "realtime"

    return {
        "now": now,
        "now_source": now_source,
        "time_scale": clock_state.time_scale,
        "clock": {
            "sim_unix_ms": int(now.timestamp() * 1000),
            "iso": now.isoformat(),
            "time_scale": clock_state.time_scale,
            "revision": clock_state.revision,
            "time_scale_revision": clock_state.time_scale_revision,
            "source": now_source,
            "display": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "bridge_status": clock_state.bridge_status,
        },
    }


def ensure_clock_fresh(*, clock_state: DashboardClockState, events_file: Path, max_age_seconds: float = 2.0) -> None:
    observed_at = clock_state.observed_at
    if observed_at is None:
        _load_clock_from_events_file(clock_state=clock_state, events_file=events_file)
        return
    if clock_state.bridge_status == "connected":
        return
    age = (datetime.now(timezone.utc) - observed_at).total_seconds()
    if age > max_age_seconds:
        _load_clock_from_events_file(clock_state=clock_state, events_file=events_file)


def _load_clock_from_events_file(*, clock_state: DashboardClockState, events_file: Path) -> None:
    if not events_file.exists():
        return
    try:
        lines = events_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        logger.exception("[dashboard_projection] clock file read failed path=%s", events_file)
        return
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == "clock":
            clock_state.update_from_message(payload)
            return


def _to_iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def _parse_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _flight_to_dict(f: Any) -> dict[str, Any]:
    return {
        "id": getattr(f, "id", None),
        "icao": getattr(f, "icao", None),
        "origin": getattr(f, "origin", None),
        "destination": getattr(f, "destination", None),
        "departure_time": _to_iso(getattr(f, "departure_time", None)),
        "arrival_time": _to_iso(getattr(f, "arrival_time", None)),
        "tipo": getattr(f, "tipo", None),
        "status": getattr(f, "status", None),
        "airplane_id": getattr(f, "airplane_id", None),
    }


def _flight_reference_time(flight: dict[str, Any], airport: str) -> tuple[datetime | None, str]:
    if flight.get("origin") == airport:
        return _parse_utc_datetime(flight.get("departure_time")), "DEP"
    return (
        _parse_utc_datetime(flight.get("arrival_time"))
        or _parse_utc_datetime(flight.get("departure_time")),
        "ARR",
    )

def _build_timeline_markers(*, now: datetime, window_minutes: int, steps: int = 6) -> list[dict[str, Any]]:
    start = now
    end = now + timedelta(minutes=window_minutes)
    total_seconds = max(1.0, (end - start).total_seconds())
    items: list[dict[str, Any]] = []
    for index in range(steps + 1):
        instant = start + ((end - start) * index / steps)
        offset_seconds = (instant - start).total_seconds()
        items.append(
            {
                "iso": instant.isoformat(),
                "label": instant.strftime("%H:%M"),
                "offset_minutes": round(offset_seconds / 60.0, 1),
                "position_pct": round((offset_seconds / total_seconds) * 100.0, 3),
            }
        )
    return items
