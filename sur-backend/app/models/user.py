from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Null for a user that only ever existed via the X-User-Email dev stub
    # (app/core/security.py) and never went through /api/auth/signup -- such
    # a user cannot log in with a password until they sign up for real.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")  # noqa: F821
