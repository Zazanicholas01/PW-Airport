from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from src.db.engine import get_engine

@dataclass
class AppContainer:
    engine: Engine
    Session: sessionmaker
    prefab_store: Any
    graph: Any
    world_state: Any

def build_container(*, prefab_store, graph, world_state) -> AppContainer:

    engine = get_engine()
    Session = sessionmaker(bind=engine, future=True)

    return AppContainer(
        engine=engine,
        Session=Session,
        prefab_store=prefab_store,
        graph=graph,
        world_state=world_state
    )