import enum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, UUIDPKMixin


class ExportStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    ready = "ready"
    failed = "failed"


class ExportJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "export_jobs"

    project_id: Mapped[str] = mapped_column(GUID, ForeignKey("projects.id"), index=True)
    # Unbounded column + CHECK constraint -- see app/models/project.py's
    # ProjectStatus.status for why a fixed-width VARCHAR is unsafe here.
    status: Mapped[ExportStatus] = mapped_column(
        Enum(ExportStatus, native_enum=False, length=None, create_constraint=True),
        default=ExportStatus.pending,
    )
    format: Mapped[str] = mapped_column(String(20), default="mp4")
    resolution: Mapped[str] = mapped_column(String(20), default="source")
    output_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # {"segments": [{"segment_id":..., "wer": ..., "sync_offset_pct": ...,
    #                "speaker_similarity": ...}], "overall": {...}}
    qa_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="export_jobs")  # noqa: F821
