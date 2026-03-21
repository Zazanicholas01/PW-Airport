from sqlalchemy import select
from src.db import models

from src.transport.command_builders import build_start_path_command
from src.domain.status_constants import DEFAULT_PLANE_SPEED

# Now constant speed CHANGE WITH DYNAMIC SPEED


def get_route_id_for_airplane(*, session, airplane_id: str) -> str | None:
    return session.execute(
        select(models.Airplane.route_id).where(models.Airplane.id == airplane_id)
    ).scalar_one_or_none()


def get_segments_for_route(*, session, route_id: str) -> list | None:
    path = session.get(models.Path, route_id)
    if path is None or not path.spline:
        return None
    return path.spline


def make_start_path_command(*, airplane_id: str, speed: float = DEFAULT_PLANE_SPEED, Session=None) -> dict | None:
    
    with Session() as session:

        # Get the route linked to the airplane
        route_id = get_route_id_for_airplane(session=session, airplane_id=airplane_id)
        if route_id is None:
            return None
        
        # Get the path from DB corresponding to the route
        segments = get_segments_for_route(session=session, route_id=route_id)
        if not segments:
            return None
        
        # Return START PATH command
        return build_start_path_command(
            airplane_id=airplane_id,
            route_id=route_id,
            segments=segments,
            speed=speed
        )
