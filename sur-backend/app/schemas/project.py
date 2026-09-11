from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    target_languages: list[str] = Field(..., min_length=1)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    target_languages: list[str]
    status: ProjectStatus
    current_stage: str | None
    preserve_emotion: bool
    clone_voice: bool
    lip_sync_aware: bool
    tts_model: str | None
    error_message: str | None
    error_is_permanent: bool | None = None
    source_language: str | None = None
    review_language: bool = True
    created_at: datetime
    updated_at: datetime


class ProjectListItem(ProjectRead):
    """Adds the fields the Dashboard screen's project cards need."""

    source_video_duration_ms: int | None = None
    segment_count: int = 0


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"


class UploadUrlResponse(BaseModel):
    source_video_id: str
    upload_url: str
    storage_key: str
    method: str = "PUT"
    expires_in: int = 3600


class UploadConfirmRequest(BaseModel):
    source_video_id: str
    duration_ms: int | None = None


class ConfirmLanguageRequest(BaseModel):
    """POST /api/projects/{id}/confirm-language.

    `source_language` overrides what ASR detected. None accepts the detection
    as-is. Either way the pipeline resumes from emotion detection onward.
    """

    source_language: str | None = None


class ProcessRequest(BaseModel):
    """Body for POST /api/projects/{id}/process -- section 05 of the PRD."""

    preserve_emotion: bool = True
    clone_voice: bool = False
    lip_sync_aware: bool = False
    tts_model: str | None = None
    # Pause after ASR so the detected source language can be confirmed before
    # the expensive stages run. Defaults to on: silently dubbing from a
    # mis-detected language is worse than one extra click.
    review_language: bool = True
