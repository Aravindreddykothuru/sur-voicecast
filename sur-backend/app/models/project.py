import enum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, UUIDPKMixin


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    uploading = "uploading"
    queued = "queued"
    processing = "processing"
    # Paused after ASR so a human can confirm/correct the detected source
    # language before the expensive stages run. A wrong auto-detect that runs
    # straight through burns a full TTS pass (~2 min/sentence on CPU) and
    # produces a dub of the wrong language.
    awaiting_language_confirmation = "awaiting_language_confirmation"
    ready = "ready"
    failed = "failed"


class Project(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))

    # Stored as a JSON array of BCP-47-ish language codes, e.g. ["te"].
    target_languages: Mapped[list[str]] = mapped_column(JSON, default=list)

    # length=None + create_constraint=True: an unbounded column (Postgres
    # treats bare VARCHAR identically to TEXT -- no size, no performance
    # difference) with a CHECK constraint enumerating the allowed values,
    # instead of a fixed-width VARCHAR. A too-long or unrecognized value is
    # now a rejected constraint violation, not a silent truncation.
    #
    # This replaces VARCHAR(10) (sized to fit "processing", the longest
    # member when 0001_initial_schema.py was written) which broke the
    # instant awaiting_language_confirmation (31 chars) was added to this
    # enum with no migration to widen the column -- SQLite doesn't enforce
    # VARCHAR length, so 137 tests stayed green while Postgres rejected
    # every write of that status. A fixed VARCHAR(64) closes today's gap but
    # is still an arbitrary ceiling the next status name can hit; this
    # doesn't have one. See migration 0005_enum_columns_text_check.py.
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=None, create_constraint=True),
        default=ProjectStatus.draft,
    )
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Feature flags -- section 05 /process request body.
    preserve_emotion: Mapped[bool] = mapped_column(Boolean, default=True)
    clone_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    lip_sync_aware: Mapped[bool] = mapped_column(Boolean, default=False)
    tts_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # True when re-running cannot help (bad input, missing row, unsupported
    # language). The UI shows "Retrying..." only for transient failures --
    # telling someone to wait for a retry that will never succeed is worse
    # than telling them nothing.
    error_is_permanent: Mapped[bool | None] = mapped_column(nullable=True)
    # Confirmed source language for ASR. None = let the model detect it.
    # Set when a reviewer overrides a wrong auto-detect.
    source_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # False lets a caller (automation, tests) skip the confirmation gate.
    review_language: Mapped[bool] = mapped_column(default=True)

    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    source_videos: Mapped[list["SourceVideo"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    speakers: Mapped[list["Speaker"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    segments: Mapped[list["Segment"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", order_by="Segment.index"
    )
    export_jobs: Mapped[list["ExportJob"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
