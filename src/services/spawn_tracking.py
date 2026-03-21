import logging
from uuid import uuid4

from sqlalchemy.orm import sessionmaker
from src.db import models
from src.db.engine import get_engine

from src.utils.mapping import (
    range_for_airplane_model,
    type_for_airplane_model
)

def ensure_airplane_row(*, Session=None, airplane_id: str | None, prefab: str) -> str:
    
    # Apre sessione DB e la chiude automaticamente alla fine
    if Session is None:
        Session = sessionmaker(bind=get_engine(), future=True)

    with Session() as session:

        # Check su DB se esiste già l'aereo, se si ritorna l'ID stesso 
        # altrimenti lo crea tramite UUID
        if airplane_id:
            existing = session.get(models.Airplane, airplane_id)

            if existing is not None:
                return airplane_id
        else:
            airplane_id = str(uuid4())

        # Utilizza funzioni da utils/mapping per range e tipo dell'aereo in base al prefab
        try:
            range_value = range_for_airplane_model(prefab)
            airplane_type = type_for_airplane_model(prefab)
        except ValueError:
            logging.warning("Unknown prefab=%r; using defaults", prefab)

            # FALLBACK
            range_value, airplane_type = "Medium", "Passengers"


        # Crea il record per creare un aereo basato sui models
            #  ID --> Esistente o generato
            #  type, range, model --> Derivati da prefab e mapping
            #  Other fields --> DEFAULT

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

        # Aggiunge in DB, log e ritorna l'ID dell'aereo creato
        session.add(airplane)
        session.commit()
        logging.info("[db] Airplane created id=%s prefab=%s", airplane_id, prefab)
        return airplane_id
