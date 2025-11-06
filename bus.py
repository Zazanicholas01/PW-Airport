import websockets, json, asyncio
from typing import Optional

class Bus:
    def __init__(self, ws: websockets.WebSocketServerProtocol):

        self.ws = ws
        self.pending_queries: dict[str, asyncio.Future] = {}
        self.pending_acks: dict[str, asyncio.Future] = {}
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self):
        self._reader_task = asyncio.create_task(self._reader())

    async def stop(self):
        if self._reader_task:
            self._reader_task.cancel()

            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def _reader(self):
        async for raw in self.ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            t = msg.get("type")

            if t == "response":
                mid = msg.get("msg_id")
                fut = self.pending_queries.pop(mid, None)
                if fut and not fut.done():
                    fut.set_result(msg)

            elif t == "event":
                ref = msg.get("ref_msg_id")
                fut = self.pending_acks.pop(ref, None) if ref else None

                if fut and not fut.done():
                    fut.set_result(msg)
                else:
                    await self.events.put(msg)

    async def send(self, payload: dict):
        await self.ws.send(json.dumps(payload))

    async def send_query(self, payload: dict) -> dict:
        mid = payload["msg_id"]
        fut = asyncio.get_event_loop().create_future()
        self.pending_queries[mid] = fut

        await self.send(payload)
        return await fut

    async def send_cmd_wait_ack(self, payload: dict) -> dict:
        mid = payload["msg_id"]
        fut = asyncio.get_event_loop().create_future()
        self.pending_acks[mid] = fut
        
        await self.send(payload)
        return await fut