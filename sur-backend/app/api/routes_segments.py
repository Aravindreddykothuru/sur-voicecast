"""PATCH /api/segments/{id} and POST /api/segments/{id}/regenerate."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owned_segment
from app.models.segment import Segment
from app.pipeline.regenerate import regenerate_segment as regenerate_segment_task
from app.schemas.common import OkResponse
from app.schemas.segment import RegenerateRequest, SegmentPatch, SegmentRead

router = APIRouter(prefix="/api/segments", tags=["segments"])


@router.patch("/{segment_id}", response_model=SegmentRead)
def patch_segment(
    body: SegmentPatch,
    db: Session = Depends(get_db),
    segment: Segment = Depends(get_owned_segment),
):
    if body.translated_text is not None:
        segment.translated_text = body.translated_text
    if body.emotion_label is not None:
        segment.emotion_label = body.emotion_label
        segment.emotion_overridden = True
    db.commit()
    db.refresh(segment)
    return segment


@router.post("/{segment_id}/regenerate", response_model=OkResponse, status_code=202)
def regenerate_segment(
    body: RegenerateRequest,
    segment: Segment = Depends(get_owned_segment),
):
    """Queues a regenerate job for this segment only; the rest of the
    project's render is untouched. Progress/result arrive as a
    `segment_ready` event on the project's WebSocket channel, same as a
    full pipeline run -- the frontend doesn't need a separate code path."""
    regenerate_segment_task.delay(segment.id, body.stages)
    return OkResponse()
