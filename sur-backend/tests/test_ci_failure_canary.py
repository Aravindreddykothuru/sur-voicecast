"""TEMPORARY. Deliberately failing, pushed to prove the CI pipeline can go
red on a backend defect. Removed in the very next commit.

A green pipeline that has never been seen to fail is not evidence of
anything: it is equally consistent with the tests running and passing, and
with them never running at all.

Two assertions, both provably false against the real system, so the job
cannot pass by accident:
  1. that the production database guard lets a dev process through, and
  2. that projects.status is still the VARCHAR(10) that caused the outage.

The second one only fails if CI really did apply the Alembic migrations to
a real Postgres, which is the part most worth proving.
"""
from __future__ import annotations

import sqlalchemy as sa

from app.config import Settings

PROD_URL = "postgresql+psycopg2://u:p@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"


def test_canary_guard_should_not_fire() -> None:
    # False: Settings raises RuntimeError here.
    Settings(environment="development", database_url=PROD_URL)


def test_canary_status_is_still_varchar_10(_pg_engine) -> None:
    with _pg_engine.connect() as conn:
        length = conn.execute(
            sa.text(
                "select character_maximum_length from information_schema.columns "
                "where table_name='projects' and column_name='status'"
            )
        ).scalar()
    # False after 0005: the column is unbounded.
    assert length == 10, f"status length is {length!r}, not 10"
