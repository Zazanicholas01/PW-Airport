import asyncio, logging, json, re
from datetime import datetime, timezone

from src.domain.prefab_store import PrefabStore
from src.init_graph import InitGraph
from src.handlers.setup_bus import SetupBusHandler
from src.handlers.runtime_bus import RuntimeBusHandler
from src.domain.world_state import WorldState
from src.domain.status_constants import *
from src.transport.ws_server import main
from src.utils.event_log import append_event

from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

_ansi = re.compile(r"\x1b\[[0-9;]*m")
_subsys = re.compile(r"^\[(?P<subsystem>[^\]]+)\]\s*")

def _clean_msg(msg: str, max_len: int = 400) -> str:
    msg = _ansi.sub("", msg)
    msg = " ".join(msg.split())
    if len(msg) > max_len:
        msg = msg[: max_len - 1] + "..."
    return msg

class EventJsonHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            raw = record.getMessage()
            raw = raw if isinstance(raw, str) else str(raw)

            subsystem = None
            m = _subsys.match(raw)
            if m:
                subsystem = m.group("subsystem")
                raw = raw[m.end():]

            evt = {
                "type": "log",
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "subsystem": subsystem,
                "message": _clean_msg(raw)
            }

            fields = getattr(record, "fields", None)
            if isinstance(fields, dict) and fields:
                evt["fields"] = fields
            
            append_event(evt)
            
        except Exception:
            pass

logging.getLogger().addHandler(EventJsonHandler())

pw_prefab_store = PrefabStore()
pw_graph = InitGraph(PERSONAL_AIRPORT)
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
                host=WEBSOCKET_CONFIG.HOST, 
                port=WEBSOCKET_CONFIG.PORT, 
                pw_prefab_store=pw_prefab_store, 
                pw_graph=pw_graph, 
                pw_world_state=pw_world_state
            )
        )
    except KeyboardInterrupt:
        logging.info("Shutting down server")
