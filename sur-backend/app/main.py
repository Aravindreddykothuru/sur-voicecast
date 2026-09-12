from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_auth,
    routes_capabilities,
    routes_health,
    routes_projects,
    routes_segments,
    routes_storage,
    ws,
)
from app.config import get_settings
from app.logging_conf import configure_logging

settings = get_settings()

# This is the process that signs and verifies session tokens and answers
# CORS preflights, so this is where the production secret rules are
# enforced -- at import, before the app can serve a single request. It is
# deliberately not a Settings validator: Alembic and Celery load Settings
# too, and making `alembic upgrade head` fail on a JWT error during a
# production migration is both confusing and an invitation to work around
# the check.
settings.require_secure_production_runtime()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sur API",
    description=(
        "Backend for Sur, an emotion-aware AI dubbing pipeline. "
        "REST under /api for project/segment CRUD and control; a WebSocket "
        "at /ws/projects/{id} for live pipeline progress. OpenAPI schema "
        "here is the contract the frontend generates its TypeScript types "
        "from (see frontend build prompt, PRD section 08)."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_capabilities.router)
app.include_router(routes_projects.router)
app.include_router(routes_segments.router)
app.include_router(routes_storage.router)
app.include_router(ws.router)


from app.db import Base, engine
from app import models as _models  # noqa: F401


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("sur-backend starting up", extra={"environment": settings.environment})
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created")
    except Exception as e:
        logger.warning("Could not auto-create database tables: %s", e)

    # Cheap, model-free invariants. The API serves /api/capabilities, so an
    # incomplete language table here would be published to every client.
    # Model loading is checked in the workers, which actually own the models.
    from app.startup_checks import verify_capabilities

    verify_capabilities()

