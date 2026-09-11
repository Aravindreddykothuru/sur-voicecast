"""Add password_hash to users for real signup/login.

Null for any user that only ever existed via the X-User-Email dev stub
(app/core/security.py) -- such a user cannot log in with a password until
they go through /api/auth/signup for real. See app/models/user.py.

Revision ID: 0003_user_password
Revises: 0002_segment_detected_language
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_user_password"
down_revision = "0002_segment_detected_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
