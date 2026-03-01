from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from src.db.engine import get_engine

@dataclass(frozen=True)
class AppContainer:
    
    engine: Engine
    Session: sessionmaker

    prefab_store: Any
    graph: Any
    world_state: Any

def build_container(*, prefab_store: Any = None, graph: Any = None, world_state: Any = None) -> AppContainer:

    engine = get_engine()
    Session = sessionmaker(bind=engine, future=True)

    return AppContainer(
        engine=engine,
        Session=Session,
        prefab_store=prefab_store,
        graph=graph,
        world_state=world_state
    )
