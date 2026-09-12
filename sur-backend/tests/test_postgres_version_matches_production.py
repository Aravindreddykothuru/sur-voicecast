"""The database under test must be the same major version as production.

This is the SQLite-vs-Postgres gap one layer down. The suite was moved to
real Postgres because SQLite did not enforce what production enforces --
and then ran Postgres 16 against a production server on 17.6, which is the
same mistake in a smaller size. It already drew blood once: pg_dump 16.14
refused to dump the 17.6 server outright. That failure was loud. The
quiet version is a 17-only behavioural difference that no test can reach
because no test runs on 17.

Deliberately asserts an exact major rather than ">= 16". A test that
passes on any version cannot notice the versions diverging, which is the
only thing it exists to notice.
"""
from __future__ import annotations

import sqlalchemy as sa

# Bump BOTH this and the images in docker-compose.test.yml / ci.yml when
# production is upgraded. Production reported 17.6 on 2026-09-11 via
#   select version()
PRODUCTION_MAJOR_VERSION = 17


def test_test_database_major_version_matches_production(_pg_engine) -> None:
    with _pg_engine.connect() as conn:
        raw = conn.execute(sa.text("show server_version")).scalar()
    major = int(str(raw).split(".")[0])
    assert major == PRODUCTION_MAJOR_VERSION, (
        f"tests are running against Postgres {raw!r} (major {major}) but production "
        f"is major {PRODUCTION_MAJOR_VERSION}. Behaviour that differs between the two "
        "is invisible to this suite. Update docker-compose.test.yml, "
        ".github/workflows/ci.yml and PRODUCTION_MAJOR_VERSION together."
    )
