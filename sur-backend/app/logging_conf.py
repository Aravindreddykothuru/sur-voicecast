"""Structured JSON logging.

Non-functional requirement from the PRD: every log line should carry
project_id/segment_id when available. We do this with a contextvar-backed
filter so pipeline code just calls `logging.getLogger(__name__)` normally and
the ids get attached automatically for the duration of a task/request.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

_project_id_ctx: ContextVar[str | None] = ContextVar("project_id", default=None)
_segment_id_ctx: ContextVar[str | None] = ContextVar("segment_id", default=None)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.project_id = _project_id_ctx.get()
        record.segment_id = _segment_id_ctx.get()
        return True


def bind_context(*, project_id: str | None = None, segment_id: str | None = None) -> None:
    if project_id is not None:
        _project_id_ctx.set(project_id)
    if segment_id is not None:
        _segment_id_ctx.set(segment_id)


def clear_context() -> None:
    _project_id_ctx.set(None)
    _segment_id_ctx.set(None)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(project_id)s %(segment_id)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Quiet down noisy third-party loggers by default.
    for noisy in ("botocore", "urllib3", "celery.worker"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
