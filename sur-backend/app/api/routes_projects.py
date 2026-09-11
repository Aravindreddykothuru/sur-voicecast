"""Project CRUD + upload + process + export -- section 05 of the PRD."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import get_current_user
from app.db import get_db
from app.deps import get_owned_project
from app.models.export_job import ExportJob
from app.models.project import Project, ProjectStatus
from app.models.segment import Segment
from app.models.source_video import SourceVideo, SourceVideoStatus
from app.models.user import User
from app.pipeline.chain import continue_pipeline, start_pipeline
from app.schemas.export import ExportRead
from app.schemas.project import (
    ConfirmLanguageRequest,
    ProcessRequest,
    ProjectCreate,
    ProjectListItem,
    ProjectRead,
    UploadConfirmRequest,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.schemas.segment import SegmentRead
from app.storage import get_storage

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectListItem])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Not in the PRD's literal endpoint table, but required by the
    Dashboard screen ("all projects, status at a glance") -- kept alongside
    the spec'd endpoints rather than left for the frontend to improvise."""
    projects = db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    ).scalars().all()

    items = []
    for p in projects:
        duration = db.execute(
            select(SourceVideo.duration_ms).where(SourceVideo.project_id == p.id).limit(1)
        ).scalar_one_or_none()
        seg_count = db.execute(
            select(func.count(Segment.id)).where(Segment.project_id == p.id)
        ).scalar_one()
        items.append(
            ProjectListItem.model_validate(p, from_attributes=True).model_copy(
                update={"source_video_duration_ms": duration, "segment_count": seg_count}
            )
        )
    return items


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(user_id=user.id, title=body.title, target_languages=body.target_languages)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project: Project = Depends(get_owned_project)):
    return project


@router.post("/{project_id}/upload", response_model=UploadUrlResponse)
def create_upload_url(
    project_id: str,
    body: UploadUrlRequest,
    db: Session = Depends(get_db),
    project: Project = Depends(get_owned_project),
):
    """Issues a presigned PUT URL straight to object storage, per the PRD's
    "presigned multipart URL" ingest design. (A single presigned PUT covers
    the MVP; swap for presigned multipart-upload parts if you need >5GB
    source files.)"""
    settings = get_settings()
    if body.content_type not in settings.accepted_video_format_list:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported content type {body.content_type!r}. Accepted: "
                f"{', '.join(settings.accepted_video_format_list)}."
            ),
        )
    storage = get_storage()
    video = SourceVideo(
        project_id=project_id,
        original_filename=body.filename,
        content_type=body.content_type,
        storage_key=f"projects/{project_id}/videos/{uuid.uuid4()}/{body.filename}",
        status=SourceVideoStatus.pending_upload,
    )
    db.add(video)
    project.status = ProjectStatus.uploading
    db.commit()
    db.refresh(video)

    url = storage.presigned_put_url(video.storage_key, body.content_type)
    return UploadUrlResponse(source_video_id=video.id, upload_url=url, storage_key=video.storage_key)


@router.post("/{project_id}/upload/confirm", response_model=ProjectRead)
def confirm_upload(
    project_id: str,
    body: UploadConfirmRequest,
    db: Session = Depends(get_db),
    project: Project = Depends(get_owned_project),
):
    """Client calls this once the presigned PUT above has completed.

    The client's own claimed size is never trusted -- only the storage
    backend's own answer (get_size) is, since that's the one place a
    presigned PUT can't be lied to. A video that cleared /upload's
    content_type check but landed oversized is rejected here rather than
    silently accepted and failing deep in extract_audio or timing out a
    worker later. See CONTRACTS.md #5.
    """
    video = db.get(SourceVideo, body.source_video_id)
    if video is None or video.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source video not found")

    settings = get_settings()
    storage = get_storage()
    try:
        size_bytes = storage.get_size(video.storage_key)
    except FileNotFoundError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Upload not found in storage -- the presigned PUT may not have completed.",
        ) from None

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        storage.delete(video.storage_key)
        video.status = SourceVideoStatus.failed
        db.commit()
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload is {size_bytes / 1024 / 1024:.0f}MB; max is {settings.max_upload_mb}MB.",
        )

    video.status = SourceVideoStatus.uploaded
    if body.duration_ms:
        video.duration_ms = body.duration_ms
    project.status = ProjectStatus.draft
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/process", response_model=ProjectRead)
def start_processing(
    project_id: str,
    body: ProcessRequest,
    db: Session = Depends(get_db),
    project: Project = Depends(get_owned_project),
):
    video = db.execute(
        select(SourceVideo)
        .where(SourceVideo.project_id == project_id, SourceVideo.status == SourceVideoStatus.uploaded)
        .order_by(SourceVideo.created_at.desc())
    ).scalars().first()
    if video is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No uploaded source video for this project")

    project.preserve_emotion = body.preserve_emotion
    project.clone_voice = body.clone_voice
    project.lip_sync_aware = body.lip_sync_aware
    project.review_language = body.review_language
    project.tts_model = body.tts_model
    project.status = ProjectStatus.queued
    project.error_message = None
    db.commit()
    db.refresh(project)

    start_pipeline(project_id, video.id)
    return project


@router.get("/{project_id}/segments", response_model=list[SegmentRead])
def list_segments(
    project_id: str,
    db: Session = Depends(get_db),
    project: Project = Depends(get_owned_project),
):
    segments = db.execute(
        select(Segment).where(Segment.project_id == project_id).order_by(Segment.index)
    ).scalars().all()
    return segments


@router.get("/{project_id}/export", response_model=ExportRead)
def get_export(
    project_id: str,
    db: Session = Depends(get_db),
    project: Project = Depends(get_owned_project),
):
    export = db.execute(
        select(ExportJob).where(ExportJob.project_id == project_id).order_by(ExportJob.created_at.desc())
    ).scalars().first()
    if export is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No export yet for this project")

    read = ExportRead.model_validate(export, from_attributes=True)
    if export.output_url:
        storage = get_storage()
        read = read.model_copy(update={"output_url": storage.presigned_get_url(export.output_url)})
    return read


@router.post("/{project_id}/confirm-language", response_model=ProjectRead)
def confirm_language(
    project_id: str,
    body: ConfirmLanguageRequest,
    db: Session = Depends(get_db),
    project: Project = Depends(get_owned_project),
):
    """Accept or correct the detected source language, then run the expensive half.

    The pipeline parks after ASR (see chain.py) precisely so this decision is
    made before minutes of TTS are spent. Passing a different `source_language`
    re-runs transcription with it first; passing none accepts the detection.
    """
    if project.status != ProjectStatus.awaiting_language_confirmation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Project is {project.status.value}, not awaiting language confirmation. "
                "This endpoint only applies to a run parked after transcription."
            ),
        )

    detected = db.execute(
        select(Segment.detected_language)
        .where(Segment.project_id == project_id, Segment.detected_language.is_not(None))
        .limit(1)
    ).scalar_one_or_none()

    override = (body.source_language or "").strip() or None
    project.status = ProjectStatus.processing
    project.error_message = None
    project.error_is_permanent = None

    if override and override != detected:
        # Corrected: redo ASR with the chosen language, then continue. The
        # transcribe stage picks up already-transcribed segments again, so the
        # text is genuinely re-derived rather than patched.
        project.source_language = override
        project.review_language = False  # don't park a second time
        db.commit()
        video = db.execute(
            select(SourceVideo)
            .where(SourceVideo.project_id == project_id)
            .order_by(SourceVideo.created_at.desc())
        ).scalars().first()
        if video is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No source video for this project")
        start_pipeline(project.id, video.id, review_language=False)
    else:
        project.source_language = detected
        db.commit()
        continue_pipeline(project.id)

    db.refresh(project)
    return project
