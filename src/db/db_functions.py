import logging
from src.db import models

from src.db.engine import get_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, or_, and_

from datetime import datetime, timedelta, timezone

_engine = get_engine()
Session = sessionmaker(bind=_engine, future=True)

def link_airplane_to_stand(*, stand_id: str, airplane_id: str) -> None:
    with Session() as session:
        stand = session.get(models.Stand, stand_id)
        if stand is None:
            logging.warning("[db] Stand not found: %s", stand_id)
            return
        stand.airplane_id = airplane_id
        session.commit()
        logging.info("[db] Linked stand %s -> airplane %s", stand_id, airplane_id)

def unlink_airplane_from_stand(*, stand_id: str, airplane_id: str | None = None) -> None:
    with Session() as session:
        stand = session.get(models.Stand, stand_id)
        if stand is None:
            logging.warning("[db] Stand not found: %s", stand_id)
            return
        if airplane_id is not None and stand.airplane_id != airplane_id:
            return
        stand.airplane_id = None
        session.commit()
        logging.info("[db] Unlinked stand %s", stand_id)

def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def list_flights_in_sliding_window(*, airport_icao: str, now_utc: datetime, window: timedelta):
    now_utc = _as_utc(now_utc)
    now_db = now_utc.astimezone(timezone.utc)
    upper = now_db + window

    with Session() as session:
        q = (
            select(models.Flight)
            .where(models.Flight.airplane_id.is_(None))
            .where(
                or_(
                    and_(
                        models.Flight.origin == airport_icao,
                        models.Flight.departure_time.is_not(None),
                        models.Flight.departure_time <= upper,
                    ),
                    and_(
                        models.Flight.destination == airport_icao,
                        models.Flight.arrival_time.is_not(None),
                        models.Flight.arrival_time <= upper,
                    ),
                )
            )
        )
        return list(session.scalars(q))