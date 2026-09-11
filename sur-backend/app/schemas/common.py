from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class OkResponse(BaseModel):
    ok: bool = True
