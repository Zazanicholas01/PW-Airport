import asyncio, json, logging
from websockets.exceptions import ConnectionClosed

from typing import Callable

class WsMessageBus:
    """
    Message Bus tra Websocket Unity e il resto del backend

    - incoming: coda di JSON ricevuti da Unity
    - outgoing: coda di JSON da inviare a Unity
    - closed: evento flag oer chiudere il bus
    - before_send: hook chiamati prima di entrare in outgoing. Possono leggere e modificare i payload
    """

    def __init__(self) -> None:

        self.incoming: asyncio.Queue = asyncio.Queue()
        self.outgoing: asyncio.Queue = asyncio.Queue()
        self._recv_task = None
        self._send_task = None
        self.closed = asyncio.Event()
        self._before_send: list[Callable[[dict], None]] = []
    

    async def start(self, websocket):
        """Avvia i task di ricezione e invio"""

        self._recv_task = asyncio.create_task(self._recv_loop(websocket))
        self._send_task = asyncio.create_task(self._send_loop(websocket))
    

    async def stop(self):
        """Ferma i task di ricezione e invio"""

        # Flag e None in outgoing per chiudere il bus
        self.closed.set()
        await self.outgoing.put(None)

        # Loop sui task creati in start() e cancellazione
        for task in (self._recv_task, self._send_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


    async def send_command(self, payload: dict) -> None:
        """Enqueue di un comando da mandare a Unity"""

        # Return se flag closed è settato
        if self.closed.is_set():
            return

        # Loop sugli hook per eventuale pre-processing
        for hook in self._before_send:
            try:
                hook(payload)
            except Exception:
                logging.exception("Outgoing hook failed for payload: %r", payload)

        # Inserisce payload nella coda outgoing
        await self.outgoing.put(payload)
    

    async def _recv_loop(self, websocket):
        """Legge dal Websocket e mette i payload JSON in incoming"""
        
        try:
            # Loop sui payload in arrivo e prova a convertire in JSON
            async for raw in websocket:
                try:
                    payload = json.loads(raw)
                except Exception:
                    logging.info("Invalid JSON from Unity")
                    continue

                # Inserisce payload JSON nella coda incoming
                await self.incoming.put(payload)

        except ConnectionClosed:
            pass

        finally:
            self.closed.set()
            await self.outgoing.put(None)
    

    async def _send_loop(self, websocket):
        """Consuma da outgoing e manda messaggi verso Unity"""
        
        while True:

            # Attende un payload dalla coda outgoing
            payload = await self.outgoing.get()
            try:
                if payload is None:
                    return
                
                # Serializza in JSON e invia tramite websocket
                await websocket.send(json.dumps(payload))

            except ConnectionClosed as e:
                logging.info("Websocket closed (%s); Stopping send Loop", e)
                return
            
            except Exception:
                logging.exception("Error sending command to Unity")

            finally:
                self.outgoing.task_done()

    def add_outgoing_hook(self, hook: Callable[[dict], None]) -> None:
        """Registra un hook e lo inserisci nella lista before_send"""
        self._before_send.append(hook)
