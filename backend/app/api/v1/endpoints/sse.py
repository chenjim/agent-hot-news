import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

router = APIRouter()


class SSEBroadcastManager:
    """Manages SSE client queues and broadcasts messages."""

    def __init__(self):
        self._queues: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._queues.add(queue)
        logger.info(f"SSE client subscribed. Total clients: {len(self._queues)}")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        async with self._lock:
            self._queues.discard(queue)
        logger.info(f"SSE client unsubscribed. Total clients: {len(self._queues)}")

    async def broadcast(self, message: dict):
        payload = f"data: {json.dumps(message, default=str)}\n\n"
        dead_queues = set()

        async with self._lock:
            queues = list(self._queues)

        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead_queues.add(queue)
            except Exception as e:
                logger.warning(f"SSE broadcast error: {e}")
                dead_queues.add(queue)

        if dead_queues:
            async with self._lock:
                for q in dead_queues:
                    self._queues.discard(q)


sse_manager = SSEBroadcastManager()


async def _event_generator(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield payload
            except asyncio.TimeoutError:
                # Send a keep-alive comment to prevent connection drop
                yield ":keep-alive\n\n"
    except asyncio.CancelledError:
        raise
    finally:
        await sse_manager.unsubscribe(queue)


@router.get("/hot-events")
async def sse_hot_events():
    """Server-Sent Events endpoint for hot events updates."""
    queue = await sse_manager.subscribe()
    return StreamingResponse(
        _event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
