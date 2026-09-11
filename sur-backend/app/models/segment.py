import enum

from sqlalchemy import Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, UUIDPKMixin


class SegmentStatus(str, enum.Enum):
    pending = "pending"
    transcribed = "transcribed"
    emotion_detected = "emotion_detected"
    translated = "translated"
    synthesized = "synthesized"
    muxed = "muxed"
    failed = "failed"


class EmotionLabel(str, enum.Enum):
    anger = "anger"
    sadness = "sadness"
    happiness = "happiness"
    fear = "fear"
    surprise = "surprise"
    neutral = "neutral"


class Segment(UUIDPKMixin, TimestampMixin, Base):
    """One utterance-level chunk of the source video.

    This is the unit the segment editor (PRD section 06) works on, and the
    unit /regenerate re-renders in isolation -- everything downstream of a
    stage keys off this row so a single-segment re-render never touches its
    siblings.
    """

    __tablename__ = "segments"

    project_id: Mapped[str] = mapped_column(GUID, ForeignKey("projects.id"), index=True)
    source_video_id: Mapped[str] = mapped_column(GUID, ForeignKey("source_videos.id"))
    speaker_id: Mapped[str | None] = mapped_column(GUID, ForeignKey("speakers.id"), nullable=True)

    index: Mapped[int] = mapped_column(Integer)  # ordering within the project
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)

    source_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # What ASR actually heard, not what anyone assumed. Persisted so the editor
    # can show a wrong auto-detect and let a reviewer correct it *before* the
    # run burns a full TTS pass. See CONTRACTS.md #5 (no silent defaults).
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detected_language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    translated_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    # Unbounded column + CHECK constraint -- see app/models/project.py's
    # ProjectStatus.status for why a fixed-width VARCHAR is unsafe here.
    emotion_label: Mapped[EmotionLabel | None] = mapped_column(
        Enum(EmotionLabel, native_enum=False, length=None, create_constraint=True), nullable=True
    )
    emotion_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    emotion_overridden: Mapped[bool] = mapped_column(default=False)

    source_audio_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tts_audio_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tts_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sync_offset_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Unbounded column + CHECK constraint -- see app/models/project.py's
    # ProjectStatus.status for why a fixed-width VARCHAR is unsafe here.
    status: Mapped[SegmentStatus] = mapped_column(
        Enum(SegmentStatus, native_enum=False, length=None, create_constraint=True),
        default=SegmentStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="segments")  # noqa: F821
    speaker: Mapped["Speaker | None"] = relationship(back_populates="segments")  # noqa: F821
