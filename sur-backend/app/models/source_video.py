import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, UUIDPKMixin


class SourceVideoStatus(str, enum.Enum):
    pending_upload = "pending_upload"
    uploaded = "uploaded"
    extracted = "extracted"
    failed = "failed"


class SourceVideo(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "source_videos"

    project_id: Mapped[str] = mapped_column(GUID, ForeignKey("projects.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(1000))
    audio_storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Unbounded column + CHECK constraint -- see app/models/project.py's
    # ProjectStatus.status for why a fixed-width VARCHAR is unsafe here.
    status: Mapped[SourceVideoStatus] = mapped_column(
        Enum(SourceVideoStatus, native_enum=False, length=None, create_constraint=True),
        default=SourceVideoStatus.pending_upload,
    )

    project: Mapped["Project"] = relationship(back_populates="source_videos")  # noqa: F821
