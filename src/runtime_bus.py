import asyncio

class RuntimeBusHandler:
    def __init__(self, simulator):
        self.simulator = simulator
        self.queue = asyncio.Queue()
        self._task = None
    
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
    
    async def handle_payload(self, payload: dict):
        pass