"""The X-User-Email stub must not be an identity in production.

get_current_user layered a real bearer token over a dev convenience: with
no Authorization header it trusted X-User-Email, looked the address up, and
created the account if it was missing. Nothing gated that on environment,
so against a production deployment

    curl -H "X-User-Email: victim@example.com" https://host/api/projects

returned the victim's projects. HTTP 200, no token, no password. The
WebSocket route took the same address as a `user_email` query parameter,
so the ownership check added for it was answering "does this email own the
project" when the open question was "is the caller this email at all".

Verified against a real uvicorn process with ENVIRONMENT=production before
the fix (200 and an accepted socket) and after (401 and a 403 handshake).
These are the regression tests for it.
"""
from __future__ import annotations

import pytest

from app.config import Settings, get_settings


@pytest.fixture
def production_env(monkeypatch):
    """Run the app as production. get_settings is lru_cached, so the cache
    is cleared on the way in AND on the way out -- leaving a production
    Settings behind would silently re-key every later test."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── the switch itself ───────────────────────────────────────────────────
@pytest.mark.parametrize("env", ["production", "PRODUCTION", " Production "])
def test_stub_is_off_in_production_however_spelled(env):
    assert Settings(environment=env).dev_email_auth_enabled is False


@pytest.mark.parametrize("env", ["development", "dev", "test", "staging", ""])
def test_stub_stays_on_everywhere_else(env):
    assert Settings(environment=env).dev_email_auth_enabled is True


def test_the_switch_has_no_override():
    """A security control with an 'enable it anyway' flag is one env var
    away from being off where it matters, so there must not be a field
    that turns it back on."""
    assert "dev_email_auth_enabled" not in Settings.model_fields


# ── the behaviour, through the real routes ──────────────────────────────
def test_header_alone_cannot_read_a_users_projects(client, production_env):
    resp = client.get("/api/projects", headers={"X-User-Email": "victim@example.com"})
    assert resp.status_code == 401, (
        f"X-User-Email alone returned {resp.status_code} in production -- this is "
        f"unauthenticated account takeover. Body: {resp.text[:200]}"
    )


def test_header_alone_cannot_create_an_account(client, production_env):
    """The stub used to INSERT unknown addresses, so an attacker could mint
    an account for an address the real owner had not registered yet."""
    from app.db import SessionLocal
    from app.models.user import User
    from sqlalchemy import select

    email = "never-signed-up@example.com"
    client.get("/api/projects", headers={"X-User-Email": email})

    db = SessionLocal()
    try:
        found = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    finally:
        db.close()
    assert found is None, "production created a user from a bare header"


def test_real_login_still_works_in_production(client, production_env):
    """The refusal has to be about the stub, not about breaking auth."""
    signup = client.post(
        "/api/auth/signup",
        json={"email": "real@example.com", "password": "S3cret-real-pw!"},  # pragma: allowlist secret
    )
    assert signup.status_code == 201, signup.text
    token = signup.json()["token"]

    resp = client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


def test_websocket_rejects_an_email_it_cannot_verify(client, production_env):
    from tests.test_cross_user_authorization import _ws_is_rejected

    signup = client.post(
        "/api/auth/signup",
        json={"email": "wsowner@example.com", "password": "S3cret-ws-pw!"},  # pragma: allowlist secret
    )
    assert signup.status_code == 201, signup.text
    token = signup.json()["token"]
    pid = client.post(
        "/api/projects",
        json={"title": "ws", "target_languages": ["te"]},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    assert _ws_is_rejected(client, f"/ws/projects/{pid}?user_email=wsowner@example.com"), (
        "production accepted a WebSocket on an unverified email -- the owner's "
        "address is not a credential"
    )
    assert not _ws_is_rejected(client, f"/ws/projects/{pid}?token={token}"), (
        "the real owner was refused his own project's events"
    )
