from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models.base import is_uuid
from app.models.project import Project
from app.models.segment import Segment
from app.models.user import User


def get_owned_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    # A malformed id can't match any row, but Postgres's uuid type raises on
    # it rather than returning nothing -- so check before querying, or a
    # typo'd URL is a 500 instead of a 404. See app/models/base.py:is_uuid.
    if not is_uuid(project_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_owned_segment(
    segment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Segment:
    if not is_uuid(segment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    segment = db.get(Segment, segment_id)
    if segment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    project = db.execute(select(Project).where(Project.id == segment.project_id)).scalar_one()
    if project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    return segment
