from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from src.db.engine import get_engine

from src.transport.command_builders import CommandBuilders, default_command_builders

@dataclass(frozen=True)
class AppContainer:
    
    engine: Engine
    Session: sessionmaker

    prefab_store: Any
    graph: Any
    world_state: Any

    commands: CommandBuilders

def build_container(*, prefab_store: Any = None, graph: Any = None, world_state: Any = None) -> AppContainer:

    engine = get_engine()
    Session = sessionmaker(bind=engine, future=True)

    return AppContainer(
        engine=engine,
        Session=Session,
        prefab_store=prefab_store,
        graph=graph,
        world_state=world_state,
        commands=default_command_builders()
    )
