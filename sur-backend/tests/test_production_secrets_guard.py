"""Production must not serve requests on the values a dev checkout ships with.

This repository is public. DEV_JWT_SECRET is therefore not merely a weak
default, it is a published one: HS256 tokens signed with a known key can be
forged for any user id. No password, no failed login, nothing unusual in a
log. Worse than the X-User-Email stub this suite already covers, and silent
rather than noisy.

The CORS case has the same shape. app/main.py sets allow_credentials=True,
and "*" with credentials lets any site on the internet make authenticated
requests as a logged-in user.

WHERE this is enforced is itself a fix. It began as a Settings validator,
which meant every process that loads config had to satisfy it -- and
`alembic upgrade head` against production then died on a JWT error, during
exactly the operation you least want to be confusing. Migrations neither
sign nor verify tokens. So the check hangs off the API's startup instead,
and the tests below pin both halves: the API refuses, and config loading
on its own does not.
"""
from __future__ import annotations

import pytest

from app.config import DEV_JWT_SECRET, MIN_JWT_SECRET_LENGTH, Settings

DEV_DB = "postgresql+psycopg2://postgres:test@localhost:5434/surdev"  # pragma: allowlist secret
GOOD_SECRET = "s" * MIN_JWT_SECRET_LENGTH  # pragma: allowlist secret


def _prod(**kw) -> Settings:
    kw.setdefault("jwt_secret_key", GOOD_SECRET)
    return Settings(environment="production", database_url=DEV_DB, **kw)


# ── what the API refuses ────────────────────────────────────────────────
def test_api_refuses_the_published_default_secret():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is still the development default"):
        _prod(jwt_secret_key=DEV_JWT_SECRET).require_secure_production_runtime()


def test_api_refuses_a_secret_short_enough_to_brute_force():
    with pytest.raises(RuntimeError, match="at least 32 are required"):
        _prod(jwt_secret_key="s" * (MIN_JWT_SECRET_LENGTH - 1)).require_secure_production_runtime()


def test_api_refuses_wildcard_cors_because_credentials_are_allowed():
    with pytest.raises(RuntimeError, match="API_CORS_ORIGINS is"):
        _prod(api_cors_origins="*").require_secure_production_runtime()


# ── what it must still allow ────────────────────────────────────────────
def test_api_accepts_a_real_secret_and_origin_list():
    """The refusals must be about the values, not about production being
    unbootable."""
    _prod(api_cors_origins="https://app.example.com").require_secure_production_runtime()


@pytest.mark.parametrize("env", ["development", "dev", "test", "staging", ""])
def test_dev_is_left_alone(env):
    """A local checkout must still start with zero configuration. Making
    developers set secrets to run tests is how a guard gets deleted."""
    Settings(environment=env, database_url=DEV_DB, api_cors_origins="*").require_secure_production_runtime()


# ── the regression this file exists for ─────────────────────────────────
def test_loading_config_in_production_does_not_require_auth_secrets():
    """Alembic and Celery load Settings too.

    When this lived in a model validator, `alembic upgrade head` against
    production raised "JWT_SECRET_KEY is still the development default" and
    exited 1. Migrations do not sign tokens, and a confusing failure during
    a production migration is how someone ends up disabling the check.
    """
    s = Settings(environment="production", database_url=DEV_DB)
    assert s.jwt_secret_key == DEV_JWT_SECRET  # constructed fine, unenforced


def test_the_check_is_not_a_model_validator():
    """Pins the design, not just the behaviour: re-adding it as a validator
    would reintroduce the Alembic break while every test above still passed.
    """
    import inspect

    from app import config as config_module

    src = inspect.getsource(config_module.Settings)
    guard_at = src.index("def require_secure_production_runtime")
    preceding = src[:guard_at].rsplit("\n", 3)[-3:]
    assert not any("model_validator" in line for line in preceding), (
        "require_secure_production_runtime is decorated as a model validator again; "
        "that makes every config load -- Alembic, Celery, scripts -- require the "
        "JWT secret."
    )


def test_the_default_and_the_guard_share_one_constant():
    assert Settings.model_fields["jwt_secret_key"].default is DEV_JWT_SECRET
