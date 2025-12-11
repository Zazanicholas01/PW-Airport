import asyncio, json, logging

class WsMessageBus:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.outgoing: asyncio.Queue = asyncio.Queue()
        self._recv_task = None
        self._send_task = None
    
    async def start(self, websocket):
        """Avvia i task di ricezione e invio"""

        self._recv_task = asyncio.create_task(self._recv_loop(websocket))
        self._send_task = asyncio.create_task(self._send_loop(websocket))
    

    async def stop(self):
        """Ferma i task di ricezione e invio"""

        for task in (self._recv_task, self._send_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


    async def send_command(self, payload: dict) -> None:
        """Enqueue di un comando da mandare a Unity"""

        await self.outgoing.put(payload)
    

    async def _recv_loop(self, websocket):
        """Legge dal Websocket e mette i payload JSON in incoming"""

        async for raw in websocket:
            try:
                payload = json.loads(raw)
            except Exception:
                logging.info("Invalid JSON from Unity")
                continue
            await self.incoming.put(payload)
    

    async def _send_loop(self, websocket):
        """Consuma da outgoing e manda messaggi verso Unity"""
        
        while True:
            payload = await self.outgoing.get()
            try:
                await websocket.send(json.dumps(payload))
            except Exception:
                logging.exception("Error sending command to Unity")
            finally:
                self.outgoing.task_done()
