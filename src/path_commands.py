from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.db.engine import get_engine
from src.db import models

Session = sessionmaker(bind=get_engine(), future=True)

DEFAULT_PLANE_SPEED = 0.2  # !!! Now constant CHANGE WITH DYNAMIC SPEED

def make_start_path_command(*, airplane_id: str, speed: float = DEFAULT_PLANE_SPEED) -> dict | None:
    
    with Session() as session:

        # Get the route linked to the airplane
        route_id = session.execute(
            select(models.Airplane.route_id).where(models.Airplane.id == airplane_id)
        ).scalar_one_or_none()

        if route_id is None:
            return None
        
        # Get the path from DB corresponding to the route
        path = session.get(models.Path, route_id)
        if path is None or not path.spline:
            return None
        
        # Return START PATH command
        return {
            "command": "start_path",
            "airplane_id": airplane_id,
            "route_id": route_id,
            "speed": speed,
            "segments": path.spline,
        }