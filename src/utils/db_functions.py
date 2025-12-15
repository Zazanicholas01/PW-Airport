import logging
from src import models

from src.database import get_engine
from sqlalchemy.orm import sessionmaker

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