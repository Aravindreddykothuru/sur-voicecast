"""Widen every enum-backed VARCHAR column to 64 chars.

0001_initial_schema.py declared these as sa.Enum(<literal list>,
native_enum=False), which SQLAlchemy renders as a plain VARCHAR sized to
whatever the longest literal was AT THE TIME -- projects.status was fixed at
VARCHAR(10) ("processing"). ProjectStatus later grew
awaiting_language_confirmation (31 chars) with no migration to widen the
column, since a migration is frozen history and never re-syncs with the
Python model. SQLite doesn't enforce VARCHAR length, so 137 passing tests
never caught this -- it surfaced as StringDataRightTruncation the first time
a real project reached that status on Postgres.

Fixes it and removes the whole bug class: every status/label column below
now has an explicit, generous fixed width (see app/models/*.py), so no
future enum addition can silently outgrow its column again.

Revision ID: 0004_widen_status_columns
Revises: 0003_user_password
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_widen_status_columns"
down_revision = "0003_user_password"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("projects", "status"),
    ("source_videos", "status"),
    ("segments", "status"),
    ("segments", "emotion_label"),
    ("export_jobs", "status"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=sa.String(length=64), existing_nullable=True)


def downgrade() -> None:
    # Deliberately not reverted to the original mismatched per-column widths
    # (10/14/16/9/7) -- shrinking a VARCHAR that may already hold longer
    # values (e.g. a project sitting in awaiting_language_confirmation)
    # would immediately break with the exact bug this migration fixes.
    pass
