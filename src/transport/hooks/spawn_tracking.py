from src.services.spawn_tracking import ensure_airplane_row
from src.db.db_functions import link_airplane_to_stand
from src.domain.status_constants import BUS_COMMANDS, LOG_EVENTS, NATURAL_LANGUAGE_LOGS, SPAWN_CONTEXT
from src.utils.runtime_logging import runtime_log

def make_spawn_tracking_hook(*, world_state, Session=None):
    def _hook(payload: dict) -> None:
        """Helper function to define an outgoing-hook that checks for spawn commands"""

        # Get payload and check for 'Spawn Plane' or 'Spawn' command, otherwise skip
        cmd = payload.get("command")
        if cmd not in (BUS_COMMANDS.SPAWN_PLANE, BUS_COMMANDS.LEGACY_SPAWN):
            return
        
        # Retrieve Stand ID and Prefab from the payload
        stand_id = payload.get("stand_id")
        prefab = payload.get("prefab")

        # Retrieve Spawn Context from the payload
        spawn_ctx = payload.get("spawn_context")

        # Get airplane ID and ensure the record exists in the DB
        airplane_id = payload.get("airplane_id") if isinstance(payload.get("airplane_id"), str) else None
        airplane_id = ensure_airplane_row(Session=Session, airplane_id=airplane_id, prefab=prefab)

        # If context bootsrap, link airplane to stand in DB
        if spawn_ctx == SPAWN_CONTEXT.BOOTSTRAP:
            link_airplane_to_stand(stand_id=stand_id, airplane_id=airplane_id)

        if not isinstance(stand_id, str) or not isinstance(prefab, str):
            return

        # Record the plane spawn in World State for caching purposes
        world_state.record_plane_spawn(
            stand_id = stand_id,
            prefab = prefab,
            position = payload.get("position"),
        )
        runtime_log(
            LOG_EVENTS.PLANE_SPAWN_LINKED,
            NATURAL_LANGUAGE_LOGS.PLANE_SPAWN_LINKED.format(
                prefab_model=prefab,
                stand=stand_id,
            ),
            airplane_id=airplane_id,
            prefab_model=prefab,
            stand=stand_id,
            spawn_context=spawn_ctx,
        )
    return _hook
