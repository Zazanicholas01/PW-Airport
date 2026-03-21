import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def run_tasks(*tasks: asyncio.Task):
    try:
        yield tasks
    finally:
        for task in tasks:
            task.cancel()
        
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass