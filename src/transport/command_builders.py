from __future__ import annotations

from typing import Any
from dataclasses import dataclass

from src.domain.status_constants import BUS_COMMANDS

def build_welcome(*, message: str) -> dict[str, Any]:
    return {
        "command": BUS_COMMANDS.WELCOME, 
        "type": BUS_COMMANDS.WELCOME, 
        "message": message
    }


def build_clock_sync(*, sync_id: int, sim_unix_ms: int, time_scale: float) -> dict[str, Any]:

    return {
        "command": BUS_COMMANDS.CLOCK_SYNC,
        "sync_id": sync_id,
        "sim_unix_ms": sim_unix_ms,
        "time_scale": time_scale
    }


def build_spawn_plane(
        *,
        prefab: str,
        stand_id: str,
        position: dict | None,
        airplane_id: str,
        spawn_context: str,
) -> dict[str, Any]:
    
    return {
        "command": BUS_COMMANDS.SPAWN_PLANE,
        "prefab": prefab,
        "stand_id": stand_id,
        "position": position,
        "airplane_id": airplane_id,
        "spawn_context": spawn_context
    }


def build_despawn_plane(*, airplane_id: str) -> dict[str, Any]:
    return {
        "command": BUS_COMMANDS.DESPAWN_PLANE,
        "airplane_id": airplane_id,
    }


def build_start_path_command(*, airplane_id: str, route_id: str, segments: list) -> dict[str, Any]:
    return {
        "command": BUS_COMMANDS.START_PATH,
        "airplane_id": airplane_id,
        "route_id": route_id,
        "segments": segments
    }

def build_continue_path_command(*, airplane_id: str, route_id: str, segments: list) -> dict[str, Any]:
    return {
        "command": BUS_COMMANDS.CONTINUE_PATH,
        "airplane_id": airplane_id,
        "route_id": route_id,
        "segments": segments,
    }

def build_clear_parking_command(*, airplane_id: str) -> dict[str, Any]:
    return {
        "command": BUS_COMMANDS.CLEAR_PARKING,
        "airplane_id": airplane_id,
    }

@dataclass
class CommandBuilders:
    welcome: callable
    clock_sync: callable
    spawn_plane: callable
    start_path: callable
    despawn_plane: callable
    continue_path: callable
    clear_parking: callable


def default_command_builders() -> CommandBuilders:
    return CommandBuilders(
        welcome=build_welcome,
        clock_sync=build_clock_sync,
        spawn_plane=build_spawn_plane,
        start_path=build_start_path_command,
        despawn_plane=build_despawn_plane,
        continue_path=build_continue_path_command,
        clear_parking=build_clear_parking_command,
    )
