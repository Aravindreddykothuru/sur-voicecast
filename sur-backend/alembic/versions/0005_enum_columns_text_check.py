"""Replace fixed-width VARCHAR(64) status/label columns with unbounded
VARCHAR (Postgres treats it identically to TEXT -- no size, no performance
difference) plus a named CHECK constraint enumerating the allowed values.

0004_widen_status_columns.py raised the ceiling from VARCHAR(10) to
VARCHAR(64) after awaiting_language_confirmation (31 chars) broke the
original column. VARCHAR(64) is still an arbitrary ceiling the next status
name can hit, and today NOTHING stops an unrelated typo'd string from being
written either (no CHECK constraint exists on any of these columns, despite
each being declared as an Enum in the model -- SQLAlchemy 2.0's
native_enum=False defaults create_constraint to False). This migration
removes the ceiling AND adds real enforcement: an unrecognized or
over-length value is now a rejected constraint violation, not a silent
truncation and not a silent acceptance either.

Constraint names match what SQLAlchemy derives from each column's Enum type
(no explicit `name=` given, so it lowercases the Python enum class name --
confirmed by compiling CreateTable against the postgresql dialect), so the
migration-drift test (test_schema_matches_migrations.py) sees this as
matching the current models, not as further drift.

Revision ID: 0005_enum_columns_text_check
Revises: 0004_widen_status_columns
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_enum_columns_text_check"
down_revision = "0004_widen_status_columns"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("projects", "status", "projectstatus",
     ["draft", "uploading", "queued", "processing", "awaiting_language_confirmation", "ready", "failed"]),
    ("source_videos", "status", "sourcevideostatus",
     ["pending_upload", "uploaded", "extracted", "failed"]),
    ("segments", "status", "segmentstatus",
     ["pending", "transcribed", "emotion_detected", "translated", "synthesized", "muxed", "failed"]),
    ("segments", "emotion_label", "emotionlabel",
     ["anger", "sadness", "happiness", "fear", "surprise", "neutral"]),
    ("export_jobs", "status", "exportstatus",
     ["pending", "running", "ready", "failed"]),
]


def upgrade() -> None:
    for table, column, constraint_name, values in _COLUMNS:
        op.alter_column(table, column, type_=sa.String(), existing_nullable=True)
        values_sql = ", ".join(f"'{v}'" for v in values)
        op.create_check_constraint(constraint_name, table, f"{column} IN ({values_sql})")


def downgrade() -> None:
    for table, column, constraint_name, _values in _COLUMNS:
        op.drop_constraint(constraint_name, table, type_="check")
        op.alter_column(table, column, type_=sa.String(length=64), existing_nullable=True)
