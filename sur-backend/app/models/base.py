import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def is_uuid(value: str | None) -> bool:
    """Whether `value` can be looked up in a GUID column at all.

    Postgres's native uuid type rejects a malformed string outright
    (InvalidTextRepresentation -> DataError), so `db.get(Project, "abc")`
    raises instead of returning None. Callers that take an id from outside
    -- a URL path, a task argument -- must check this first and treat a
    malformed id as "not found", which is what it is. SQLite stores these
    as CHAR(36) and quietly returns no rows instead, which is why this went
    unnoticed: a bad id was a clean 404 in tests and a 500 in production.
    """
    if not value:
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# Native uuid on Postgres (what production runs); CHAR(36) under SQLite.
# The SQLite variant is only still here because Alembic migrations render
# it for non-Postgres backends -- the test suite itself runs on Postgres
# (tests/conftest.py), precisely so differences like the one above surface.
GUID = UUID(as_uuid=False).with_variant(String(36), "sqlite")


class UUIDPKMixin:
    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=gen_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


__all__ = ["Base", "UUIDPKMixin", "TimestampMixin", "gen_uuid"]
