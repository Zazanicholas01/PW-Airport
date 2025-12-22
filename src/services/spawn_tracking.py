import logging
from uuid import uuid4

from sqlalchemy.orm import sessionmaker
from src.db import models
from src.db.engine import get_engine

from src.utils.mapping import (
    range_for_airplane_model,
    type_for_airplane_model
)

_engine = get_engine()
SessionLocal = sessionmaker(bind=_engine, future=True)

def ensure_airplane_row(*, airplane_id: str | None, prefab: str) -> str:
    with SessionLocal() as session:
        if airplane_id:
            existing = session.get(models.Airplane, airplane_id)
            if existing is not None:
                return airplane_id
        else:
            airplane_id = str(uuid4())

        range_value = range_for_airplane_model(prefab)
        airplane_type = type_for_airplane_model(prefab)

        airplane = models.Airplane(
            id=airplane_id,
            type=airplane_type,
            range=range_value,
            model=prefab,
            capacity=100,
            status="Parked",
            speed=0.0,
            fuel_level=1.0,
            maintenance=False,
            airline_code=None,
            route_id=None,
        )
        session.add(airplane)
        session.commit()
        logging.info("[db] Airplane created id=%s prefab=%s", airplane_id, prefab)
        return airplane_id

