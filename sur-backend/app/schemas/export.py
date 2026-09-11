from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.export_job import ExportStatus


class ExportRequest(BaseModel):
    format: str = "mp4"
    resolution: str = "source"


class ExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    status: ExportStatus
    format: str
    resolution: str
    output_url: str | None
    qa_report: dict | None
    created_at: datetime
    completed_at: datetime | None
