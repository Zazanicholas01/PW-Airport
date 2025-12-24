import asyncio, logging

from src.domain.prefab_store import PrefabStore
from src.init_graph import InitGraph
from src.handlers.setup_bus import SetupBusHandler
from src.handlers.runtime_bus import RuntimeBusHandler
from src.domain.world_state import WorldState
from src.transport.ws_server import main

from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

HOST = "0.0.0.0"
PORT = 8765

pw_prefab_store = PrefabStore()
pw_graph = InitGraph("LIAG")
pw_world_state = WorldState()
#logging.getLogger().setLevel(logging.DEBUG)

_engine = get_engine()
Session = sessionmaker(bind=_engine, future=True)

setup_bus: SetupBusHandler | None = None
runtime_bus: RuntimeBusHandler | None = None


if __name__ == "__main__":
    try:
        asyncio.run(
            main(
                host=HOST, 
                port=PORT, 
                pw_prefab_store=pw_prefab_store, 
                pw_graph=pw_graph, 
                pw_world_state=pw_world_state
            )
        )
    except KeyboardInterrupt:
        logging.info("Shutting down server")
