"""Test fixtures.

The suite runs against real Postgres, on purpose. SQLite does not enforce
column widths, foreign keys, NOT NULL on existing rows, unique constraints,
CHECK constraints, or transaction isolation the way Postgres does -- that
gap is exactly what let projects.status ship as VARCHAR(10) in production
(sized for "processing") while 137 SQLite-backed tests stayed green, until
a real project tried to write "awaiting_language_confirmation" (31 chars)
and Postgres rejected it. See CONTRACTS.md and the migration-drift test in
test_schema_matches_migrations.py.

There is no SQLite fallback here, and there must not be one added back:
TEST_DATABASE_URL is required with no default, and a sqlite:/// value is a
hard error. A silent fallback is how this exact gap reopens.

Everything else runs with no external services: Celery's eager mode
instead of a real Redis broker/worker, an in-memory storage double instead
of MinIO/S3, and mock providers (the default anyway) instead of any ML
model. Only the database itself needs to be the real thing.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

_TEST_DB_ENV = "TEST_DATABASE_URL"


def _require_postgres_test_database_url() -> str:
    try:
        url = os.environ[_TEST_DB_ENV]
    except KeyError as exc:
        raise RuntimeError(
            f"{_TEST_DB_ENV} is not set. This suite requires a real Postgres "
            "instance -- see docker-compose.test.yml (`docker compose -f "
            "docker-compose.test.yml up -d` gives you one on :5434) -- and "
            "will not silently fall back to anything else. Set it, e.g.:\n"
            "  TEST_DATABASE_URL=postgresql+psycopg2://postgres:test@localhost:5434/test"
        ) from exc
    if url.startswith("sqlite"):
        raise RuntimeError(
            "TEST_DATABASE_URL is a sqlite:// URL. Tests must run against Postgres: "
            "SQLite does not enforce column widths, foreign keys, NOT NULL, unique, "
            "or CHECK constraints -- that gap is exactly what let projects.status "
            "ship as VARCHAR(10) in production while every SQLite-backed test stayed "
            "green. Point this at a real Postgres instance instead."
        )
    return url


# Set before anything calls get_settings() (which is @lru_cache'd), so
# Settings.database_url and Alembic's env.py (which reads it too) agree with
# every fixture below on which database is actually under test.
_TEST_DATABASE_URL = _require_postgres_test_database_url()
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ.setdefault("ASR_PROVIDER", "mock")
os.environ.setdefault("DIARIZATION_PROVIDER", "mock")
os.environ.setdefault("TRANSLATION_PROVIDER", "mock")
os.environ.setdefault("EMOTION_PROVIDER", "mock")
os.environ.setdefault("TTS_PROVIDER", "mock")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.db import Base
from app import models  # noqa: F401 -- registers tables on Base.metadata
from app.celery_app import celery_app
from app.pipeline import events as events_module
from app.storage.base import StorageBackend

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def _pg_engine():
    """One engine for the whole run, schema built from the real Alembic
    migrations -- NOT Base.metadata.create_all(). create_all builds tables
    straight from the current models, so a model that drifted from its
    migration (exactly today's bug: the model's Enum length didn't match
    what 0001_initial_schema.py actually put in Postgres) would stay
    invisible. Migrations are what production runs; this suite must run
    the same ones."""
    cfg = Config(os.path.join(_BACKEND_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_ROOT, "alembic"))
    command.upgrade(cfg, "head")

    engine = create_engine(_TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_database(_pg_engine, monkeypatch):
    """Reset DATA between tests; the schema (built once from migrations by
    _pg_engine) stays put.

    Deliberately NOT the transaction-rollback recipe, which is the faster
    and more usual choice: it requires every session to share one
    Connection, and TestClient runs API routes on a separate thread
    (anyio's BlockingPortal), so a Celery task on the main thread and a
    route handler on the portal thread would be driving the same
    non-thread-safe Connection concurrently. That produced real, confusing
    failures -- a committed source_language that the very next stage
    couldn't see. TRUNCATE instead: app code then uses its ordinary engine
    and connection pool, committing for real exactly as it does in
    production, which is the point of testing against Postgres at all.
    """
    monkeypatch.setattr(db_module, "engine", _pg_engine)
    monkeypatch.setattr(
        db_module,
        "SessionLocal",
        sessionmaker(bind=_pg_engine, autoflush=False, autocommit=False, future=True),
    )

    yield _pg_engine

    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with _pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _celery_eager():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture(autouse=True)
def _in_memory_event_bus():
    bus = events_module.InMemoryEventBus()
    events_module.set_event_bus(bus)
    yield bus


class InMemoryStorage(StorageBackend):
    """Test double: keeps "uploaded" files on local disk instead of S3."""

    def __init__(self) -> None:
        import tempfile

        self._root = tempfile.mkdtemp(prefix="sur-test-storage-")
        self._data: dict[str, str] = {}

    def presigned_put_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return f"https://fake-storage.test/put/{key}"

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://fake-storage.test/get/{key}"

    def upload_file(self, key: str, local_path: str, content_type: str | None = None) -> None:
        import shutil

        dest = f"{self._root}/{key.replace('/', '_')}"
        shutil.copyfile(local_path, dest)
        self._data[key] = dest

    def download_file(self, key: str, local_path: str) -> None:
        import shutil

        shutil.copyfile(self._data[key], local_path)

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def get_size(self, key: str) -> int:
        import os

        if key not in self._data:
            raise FileNotFoundError(f"no object at key {key!r}")
        return os.path.getsize(self._data[key])


@pytest.fixture
def fake_storage(monkeypatch) -> Iterator[InMemoryStorage]:
    storage = InMemoryStorage()
    monkeypatch.setattr("app.storage.get_storage", lambda: storage)
    monkeypatch.setattr("app.pipeline.tasks.get_storage", lambda: storage)
    monkeypatch.setattr("app.pipeline.regenerate.get_storage", lambda: storage)
    monkeypatch.setattr("app.api.routes_projects.get_storage", lambda: storage)
    yield storage


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c
