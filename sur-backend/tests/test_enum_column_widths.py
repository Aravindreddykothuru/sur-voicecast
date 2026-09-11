"""Every Enum(..., native_enum=False) column must be unbounded (no
VARCHAR(n) ceiling) and back it with a real CHECK constraint -- never a
fixed-width column relying on the Python enum's current longest member.

History: projects.status was created (0001_initial_schema.py) as
sa.Enum("draft", "uploading", ..., native_enum=False) with no explicit
length, which SQLAlchemy renders as VARCHAR(10) -- the length of
"processing", the longest literal AT THAT TIME. ProjectStatus later grew
awaiting_language_confirmation (31 chars); nothing re-synced the frozen
migration's column width with the growing Python enum, and SQLite doesn't
enforce VARCHAR length, so the full test suite passed while the real
Postgres column would truncate-reject the very first project to reach that
status.

The first fix (VARCHAR(64)) raised the ceiling but kept the same shape of
bug possible for the next status name. This is the real fix: an unbounded
column (Postgres treats bare VARCHAR identically to TEXT) plus a CHECK
constraint enumerating the exact allowed values, so an unrecognized or
over-length value is a rejected constraint violation -- loud and immediate
-- never a silent truncation or a silent acceptance. Pure SQLAlchemy
metadata introspection, no database connection, so it catches the mismatch
on every backend, including SQLite, where the original bug was invisible.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import Enum as SAEnum

from app import models  # noqa: F401 -- registers every table on Base.metadata
from app.db import Base


def _enum_columns():
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, SAEnum):
                yield table, column, column.type


def test_every_enum_column_is_unbounded_not_fixed_width():
    found = list(_enum_columns())
    assert found, "expected at least one Enum(native_enum=False) column in the schema"
    for table, column, coltype in found:
        assert coltype.length is None, (
            f"{table.name}.{column.name} is VARCHAR({coltype.length}) -- a fixed-width "
            "column sized to fit today's enum values will break the moment a longer "
            "value is added (see app/models/project.py's ProjectStatus.status). Use "
            "length=None (Postgres renders this as unbounded VARCHAR, identical to TEXT) "
            "instead of sizing it to whatever the enum currently contains."
        )


def test_every_enum_column_has_a_check_constraint_enumerating_its_values():
    """The other half of the fix: without this, an unbounded column would
    silently accept ANY string, not just the enum's real values."""
    for table, column, coltype in _enum_columns():
        assert coltype.create_constraint is True, (
            f"{table.name}.{column.name}'s Enum type has create_constraint=False -- "
            "that's SQLAlchemy 2.0's default, and it means no CHECK constraint gets "
            "created at all, so any string fits. Pass create_constraint=True explicitly."
        )
        checks = [c for c in table.constraints if isinstance(c, CheckConstraint) and c.name == coltype.name]
        assert checks, (
            f"{table.name}.{column.name}: expected a CHECK constraint named {coltype.name!r} "
            f"on {table.name}, found none. Constraint names on this table: "
            f"{[c.name for c in table.constraints if isinstance(c, CheckConstraint)]}"
        )
