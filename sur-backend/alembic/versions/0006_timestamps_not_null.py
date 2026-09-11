"""Make every created_at/updated_at NOT NULL, matching the models.

Found by test_schema_matches_migrations.py on its first run against real
Postgres. TimestampMixin declares these as Mapped[datetime] -- non-optional,
i.e. NOT NULL -- but 0001_initial_schema.py created them without
nullable=False, so the migrated schema has allowed NULL in all six tables
since the beginning. SQLite doesn't enforce it either, which is why 137
green tests never noticed the models and the database disagreeing.

Safe to tighten: every one of these columns has server_default=now(), so
existing rows are already populated. The guard below still checks rather
than assuming -- if any NULL did exist, failing here with a clear message
beats an ALTER that errors halfway through.

Revision ID: 0006_timestamps_not_null
Revises: 0005_enum_columns_text_check
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_timestamps_not_null"
down_revision = "0005_enum_columns_text_check"
branch_labels = None
depends_on = None

_TABLES = ["users", "projects", "source_videos", "speakers", "segments", "export_jobs"]
_COLUMNS = ["created_at", "updated_at"]


def upgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        for column in _COLUMNS:
            nulls = conn.execute(
                sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')
            ).scalar_one()
            if nulls:
                raise RuntimeError(
                    f"{table}.{column} has {nulls} NULL row(s); backfill them before "
                    "this migration can set the column NOT NULL."
                )
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
                existing_server_default=sa.text("now()"),
            )


def downgrade() -> None:
    for table in _TABLES:
        for column in _COLUMNS:
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
                existing_server_default=sa.text("now()"),
            )
