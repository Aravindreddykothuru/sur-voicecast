"""A non-production process must refuse to open the production database.

This is a crash rather than a warning because the convention -- "don't point
your local .env at prod" -- already failed in practice. One Supabase instance
served both dev and production, and during a debugging session migrations
were applied and rows were deleted against the database holding real users.
Nothing in the code objected, because nothing was watching.

The guard lives on Settings, so every process that loads config gets it:
API, Celery workers, alembic, and one-off scripts alike.
"""
from __future__ import annotations

import pytest

from app.config import MIN_JWT_SECRET_LENGTH, Settings

# Production also refuses the shipped JWT default and wildcard CORS (see
# test_production_secrets_guard.py). These cases are about the DATABASE
# guard, so they supply a real secret to isolate it -- otherwise they would
# pass or fail for the wrong reason.
PROD_SECRET = "d" * MIN_JWT_SECRET_LENGTH  # pragma: allowlist secret

PROD_URLS = [
    "postgresql+psycopg2://u:p@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres",
    "postgresql+psycopg2://u:p@db.bwwdpjkdxmgfdlyffgzr.supabase.co:5432/postgres",
]

SAFE_URLS = [
    "postgresql+psycopg2://postgres:test@localhost:5434/surdev",  # pragma: allowlist secret
    "postgresql+psycopg2://postgres:test@127.0.0.1:5434/test",  # pragma: allowlist secret
]


@pytest.mark.parametrize("url", PROD_URLS)
@pytest.mark.parametrize("env", ["development", "dev", "test", "staging", ""])
def test_refuses_to_boot_against_production_outside_production(url, env):
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        Settings(environment=env, database_url=url)


@pytest.mark.parametrize("url", PROD_URLS)
def test_production_environment_is_allowed_through(url):
    """The guard must not make production itself unbootable."""
    s = Settings(environment="production", database_url=url, jwt_secret_key=PROD_SECRET)
    assert s.database_url == url


@pytest.mark.parametrize("url", SAFE_URLS)
@pytest.mark.parametrize("env", ["development", "production"])
def test_non_production_hosts_are_always_allowed(url, env):
    s = Settings(environment=env, database_url=url, jwt_secret_key=PROD_SECRET)
    assert s.database_url == url


def test_guard_is_case_insensitive_about_the_environment_name():
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        Settings(environment="Development", database_url=PROD_URLS[0])
    # ...and about the host
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        Settings(
            environment="development",
            database_url="postgresql+psycopg2://u:p@AWS-0-AP-SOUTHEAST-2.POOLER.SUPABASE.COM:5432/postgres",  # pragma: allowlist secret
        )


# ── The other direction: the test suite must refuse production ──────────
#
# Settings' guard above has a deliberate escape hatch -- ENVIRONMENT=production
# is allowed through, because production has to connect to production. The
# test suite has no such case. conftest resets state with TRUNCATE ... CASCADE
# on every table after every test, so aiming TEST_DATABASE_URL at Supabase
# does not fail loudly; it succeeds, and empties the database. These assert
# the second guard, the one in conftest, which refuses unconditionally.

from tests.conftest import _require_postgres_test_database_url  # noqa: E402


@pytest.mark.parametrize("url", PROD_URLS)
def test_test_suite_refuses_production_even_in_production(url, monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="REFUSING TO RUN"):
        _require_postgres_test_database_url()


@pytest.mark.parametrize("url", SAFE_URLS)
def test_test_suite_accepts_a_disposable_database(url, monkeypatch):
    """The refusal has to be about the host, not about rejecting everything."""
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    assert _require_postgres_test_database_url() == url


def test_test_suite_still_refuses_sqlite(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite:///./sur.db")
    with pytest.raises(RuntimeError, match="sqlite"):
        _require_postgres_test_database_url()


def test_test_suite_refuses_a_missing_url(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="is not set"):
        _require_postgres_test_database_url()
