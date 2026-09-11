from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.segment import EmotionLabel, SegmentStatus


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    speaker_id: str | None
    index: int
    start_ms: int
    end_ms: int
    source_text: str | None
    detected_language: str | None
    detected_language_confidence: float | None
    translated_text: str | None
    emotion_label: EmotionLabel | None
    emotion_score: float | None
    emotion_overridden: bool
    source_audio_url: str | None
    tts_audio_url: str | None
    tts_duration_ms: int | None
    sync_offset_pct: float | None
    status: SegmentStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SegmentPatch(BaseModel):
    """PATCH /api/segments/{id} -- edit translated text or override emotion.

    All fields optional; only provided fields are updated. Editing either
    field does NOT itself trigger a re-render -- call /regenerate for that,
    so a reviewer can queue up several text edits before spending a TTS call.
    """

    translated_text: str | None = Field(default=None, max_length=4000)
    emotion_label: EmotionLabel | None = None


class RegenerateRequest(BaseModel):
    """POST /api/segments/{id}/regenerate.

    `stages` lets the caller ask for exactly what changed -- editing text
    only needs ["synthesize"]; overriding the emotion label needs it too
    (to re-condition synthesis) but never needs ["transcribe"]. Defaults to
    re-running translate+synthesize, matching the PRD's "re-run translation
    and/or TTS for one segment only".
    """

    stages: list[str] = Field(default_factory=lambda: ["translate", "synthesize"])
