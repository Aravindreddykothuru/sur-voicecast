"""Single-segment regeneration -- POST /api/segments/{id}/regenerate.

Deliberately NOT a Celery chain of the full-project tasks: those operate on
"all segments in status X" and would either skip this one segment (if its
status doesn't match) or require resetting its status first (racy against
whatever else is touching the project). Instead this runs the requested
stages synchronously against exactly one segment, reusing the same
provider-calling helpers the full-project tasks use, so behavior never
drifts between the two paths.

Runs as its own Celery task (own queue-agnostic, routed like the stage it's
closest to -- q.synthesize, the most expensive stage it can touch) so a
regenerate request doesn't block the API request thread on a TTS render.
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.db import session_scope
from app.logging_conf import bind_context, clear_context
from app.models.project import Project
from app.models.base import is_uuid
from app.models.segment import Segment
from app.pipeline.events import emit_error, emit_segment_ready, emit_stage_completed, emit_stage_started
from app.pipeline.tasks import synthesize_segment, translate_segment
from app.storage import get_storage

logger = logging.getLogger(__name__)

VALID_STAGES = {"translate", "synthesize"}


@celery_app.task(
    bind=True,
    name="app.pipeline.regenerate.regenerate_segment",
    queue="q.synthesize",
    autoretry_for=(Exception,),
    dont_autoretry_for=(ValueError, LookupError, TypeError),
    max_retries=3,
    retry_backoff=True,
)
def regenerate_segment(self, segment_id: str, stages: list[str]) -> str:
    requested = [s for s in stages if s in VALID_STAGES] or ["translate", "synthesize"]

    with session_scope() as db:
        # Check before querying: Postgres's uuid type raises DataError on a
        # malformed id, and DataError isn't in _PERMANENT, so the task would
        # burn three retries with backoff on an id that can never be valid.
        if not is_uuid(segment_id):
            raise ValueError(f"segment {segment_id} not found")
        segment = db.get(Segment, segment_id)
        if segment is None:
            raise ValueError(f"segment {segment_id} not found")
        project = db.get(Project, segment.project_id)
        project_id = project.id

    bind_context(project_id=project_id, segment_id=segment_id)
    emit_stage_started(project_id, "regenerate")
    try:
        with session_scope() as db:
            segment = db.get(Segment, segment_id)
            project = db.get(Project, segment.project_id)

            if "translate" in requested:
                if not project.target_languages:
                    raise ValueError(f"project {project.id} has no target_languages configured")
                target_lang = project.target_languages[0]
                # Same rule as the full-project translate stage: never guess
                # a source language. Confirmed project.source_language wins;
                # this segment's own ASR detection is the fallback.
                source_lang = project.source_language or segment.detected_language
                if not source_lang:
                    raise ValueError(
                        f"segment {segment.id} has no confirmed or detected source "
                        "language -- cannot translate without guessing."
                    )
                translate_segment(segment, target_lang, source_lang)

            if "synthesize" in requested:
                storage = get_storage()
                synthesize_segment(db, storage, segment, project)

        emit_segment_ready(project_id, segment_id)
        emit_stage_completed(project_id, "regenerate")
        return segment_id
    except Exception as exc:  # noqa: BLE001
        emit_error(project_id, "regenerate", str(exc))
        raise
    finally:
        clear_context()
