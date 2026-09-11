from pydantic import BaseModel, ConfigDict


class SpeakerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    reference_clip_url: str | None
    consent_captured: bool
