from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, UUIDPKMixin


class Speaker(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "speakers"

    project_id: Mapped[str] = mapped_column(GUID, ForeignKey("projects.id"), index=True)
    label: Mapped[str] = mapped_column(String(100), default="Speaker")
    diarization_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Voice-cloning reference (P3). embedding_ref points at wherever the
    # configured TTSProvider persists its speaker embedding (a storage key,
    # a vector-store id -- provider-defined, treated as opaque here).
    embedding_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reference_clip_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    consent_captured: Mapped[bool] = mapped_column(default=False)

    project: Mapped["Project"] = relationship(back_populates="speakers")  # noqa: F821
    segments: Mapped[list["Segment"]] = relationship(back_populates="speaker")  # noqa: F821
