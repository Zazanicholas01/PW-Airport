import asyncio, logging

from sqlalchemy.orm import sessionmaker

from src.flight_generator import RandomFlightGenerator

from src.database import get_engine

_engine = get_engine()
Session = sessionmaker(bind=_engine, future=True)
class RuntimeBusHandler:
    def __init__(self, simulator, session_factory: sessionmaker | None = None):
        self.simulator = simulator
        self.queue = asyncio.Queue()
        self._task = None

        self.Session = session_factory or Session
        self._flight_generator = RandomFlightGenerator(self.Session)
    

    async def start(self):
        if self._task is None or self._task_done():
            self._flight_generator.generate_flights(10)
            logging.info("Generated Random Flights")
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
    

    async def handle_payload(self, payload: dict):
        pass