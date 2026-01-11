import asyncio, logging

from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from src.services.flight_generator import RandomFlightGenerator
from src.db import models

from src.db.engine import get_engine

_engine = get_engine()
Session = sessionmaker(bind=_engine, future=True)
class RuntimeBusHandler:
    def __init__(self, prefab_store, session_factory: sessionmaker | None = None):
        self.prefab_store = prefab_store
        self.queue = asyncio.Queue()
        self._task = None

        self.Session = session_factory or Session
        self._flight_generator = RandomFlightGenerator(self.Session)
    

    async def start(self):
        if self._task is None or self._task_done():
            self._task = asyncio.create_task(self._event_loop())
    

    async def enqueue(self, payload: dict):
        await self.queue.put(payload)
    

    async def _event_loop(self):
        while True:
            payload = await self.queue.get()
            try:
                await self.handle_payload(payload)
            finally:
                self.queue.task_done()
    
    def _find_stand_id_by_airplane_id(self, session, airplane_id: str) -> str | None:
        return session.execute(
            select(models.Stand.id).where(models.Stand.airplane_id == airplane_id)
        ).scalar_one_or_none()

    async def handle_payload(self, payload: dict):
        if payload.get("type") != "event":
            return

        evt = payload.get("event")
        airplane_id = payload.get("airplane_id")
        if not isinstance(airplane_id, str) or not airplane_id:
            return

        with self.Session() as session:
            stand_id = self._find_stand_id_by_airplane_id(session, airplane_id)

        if evt == "plane_parked":
            #### Implementare logica di atterraggio ########
            return

        if evt == "plane_left_stand":
            if stand_id is None:
                return
            stand = session.get(models.Stand, stand_id)
            if stand is None:
                return
            if stand.airplane_id != airplane_id:
                return
            stand.airplane_id = None
            session.commit()
            return
