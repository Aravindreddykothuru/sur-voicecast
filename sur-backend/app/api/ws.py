"""WebSocket gateway: one channel per project, /ws/projects/{id}.

Subscribes to the project's Redis pub/sub channel (see app/pipeline/events.py)
and forwards every message verbatim to the connected client(s) as JSON.
Multiple browser tabs/viewers on the same project each get their own
subscriber -- Redis pub/sub fans out to all of them for free.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.pipeline.events import channel_name

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/projects/{project_id}")
async def project_events(websocket: WebSocket, project_id: str):
    await websocket.accept()
    settings = get_settings()

    try:
        redis_client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        pubsub = redis_client.pubsub()
        await asyncio.wait_for(pubsub.subscribe(channel_name(project_id)), timeout=2.0)
    except Exception as e:
        logger.warning("Redis unavailable for project %s websocket: %s; running in keepalive mode", project_id, e)
        # Send initial connected message to frontend
        await websocket.send_text('{"type":"connected","status":"online","redis":"offline"}')
        try:
            while True:
                await asyncio.sleep(20)
                await websocket.send_text('{"type":"ping"}')
        except (WebSocketDisconnect, asyncio.CancelledError):
            logger.info("client disconnected from project %s events (keepalive)", project_id)
        return

    async def forward() -> None:
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                text = data.decode() if isinstance(data, bytes) else data
                await websocket.send_text(text)
        except Exception:
            pass

    forward_task = asyncio.create_task(forward())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("client disconnected from project %s events", project_id)
    finally:
        forward_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await forward_task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel_name(project_id))
            await pubsub.close()
            await redis_client.close()

