"""The one test that would have caught the original bug directly: the
schema Alembic actually builds in Postgres must match what the current
SQLAlchemy models declare. Any drift between them -- a model changed
without a migration, or a migration that doesn't produce what the model
now expects -- fails here immediately, on every run, with no database
value ever needing to hit the wrong-shaped column first.

This is what should have failed the day awaiting_language_confirmation was
added to ProjectStatus without a migration to match: the model would have
said "this column needs to hold up to 31 characters" while the real,
migrated table said VARCHAR(10), and compare_metadata would have reported
that mismatch as a type diff -- long before any project ever reached that
status in production.
"""
from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from app import models  # noqa: F401 -- registers every table on Base.metadata
from app.db import Base


def test_models_match_migrations(_pg_engine):
    with _pg_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], (
        "The Postgres schema built from alembic upgrade head does not match "
        "the current SQLAlchemy models. Every schema change needs a migration -- "
        f"write one for the difference(s) below:\n{diff}"
    )
