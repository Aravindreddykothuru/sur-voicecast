"""Progress events: stage_started / stage_progress / stage_completed /
segment_ready / error -- published on a per-project Redis pub/sub channel
and forwarded verbatim to WebSocket clients subscribed to
/ws/projects/{id} (see app/api/ws.py).

Abstracted behind EventBus so pipeline code and tests don't need a live
Redis: tests substitute InMemoryEventBus (see tests/conftest.py).
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

import redis

from app.config import get_settings


def channel_name(project_id: str) -> str:
    return f"sur:project:{project_id}:events"


class EventBus(ABC):
    @abstractmethod
    def publish(self, project_id: str, event: dict[str, Any]) -> None: ...


class RedisEventBus(EventBus):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = redis.Redis.from_url(settings.redis_url)

    def publish(self, project_id: str, event: dict[str, Any]) -> None:
        payload = {**event, "ts": time.time()}
        self._client.publish(channel_name(project_id), json.dumps(payload))


class InMemoryEventBus(EventBus):
    """Test/dev double: records events instead of publishing them."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish(self, project_id: str, event: dict[str, Any]) -> None:
        self.events.append((project_id, {**event, "ts": time.time()}))


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = RedisEventBus()
    return _bus


def set_event_bus(bus: EventBus) -> None:
    """Test hook -- see tests/conftest.py."""
    global _bus
    _bus = bus


def emit_stage_started(project_id: str, stage: str) -> None:
    get_event_bus().publish(project_id, {"type": "stage_started", "stage": stage})


def emit_stage_progress(
    project_id: str,
    stage: str,
    progress: float,
    detail: str | None = None,
    *,
    completed: int | None = None,
    total: int | None = None,
) -> None:
    """`completed`/`total` let the UI say "TTS 4/17" instead of a bare
    percentage -- on CPU a synthesis stage runs for minutes per sentence, and
    a spinner with no counts is unusable at that duration."""
    get_event_bus().publish(
        project_id,
        {
            "type": "stage_progress",
            "stage": stage,
            "progress": progress,
            "detail": detail,
            "completed": completed,
            "total": total,
        },
    )


def emit_stage_completed(project_id: str, stage: str) -> None:
    get_event_bus().publish(project_id, {"type": "stage_completed", "stage": stage})


def emit_segment_ready(project_id: str, segment_id: str) -> None:
    get_event_bus().publish(project_id, {"type": "segment_ready", "segment_id": segment_id})


def emit_error(project_id: str, stage: str, message: str, *, permanent: bool = False) -> None:
    """`permanent` tells the UI whether a retry could ever help."""
    get_event_bus().publish(
        project_id,
        {"type": "error", "stage": stage, "message": message, "permanent": permanent},
    )
