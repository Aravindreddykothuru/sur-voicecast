"""Persist the language ASR actually detected, plus its confidence.

Without these the editor cannot show a wrong auto-detect, so a
mis-detected source language silently burns a full ASR->TTS run before
anyone notices. See CONTRACTS.md #5.

Revision ID: 0002_segment_detected_language
Revises: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_segment_detected_language"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("segments", sa.Column("detected_language", sa.String(length=16), nullable=True))
    op.add_column("segments", sa.Column("detected_language_confidence", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("error_is_permanent", sa.Boolean(), nullable=True))
    op.add_column("projects", sa.Column("source_language", sa.String(length=16), nullable=True))
    op.add_column(
        "projects",
        sa.Column("review_language", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("projects", "review_language")
    op.drop_column("projects", "source_language")
    op.drop_column("projects", "error_is_permanent")
    op.drop_column("segments", "detected_language_confidence")
    op.drop_column("segments", "detected_language")
