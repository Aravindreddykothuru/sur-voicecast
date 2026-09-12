"""Production must not run on the values a dev checkout ships with.

This repository is public. DEV_JWT_SECRET is therefore not merely a weak
default, it is a published one: HS256 tokens signed with a known key can be
forged for any user id. No password, no failed login, nothing unusual in a
log. That is a worse hole than the X-User-Email stub this suite already
covers, and it is invisible rather than noisy.

The CORS case is the same shape. `app/main.py` sets
allow_credentials=True, and "*" combined with credentials lets any site on
the internet make authenticated requests as a logged-in user.

Both crash at startup rather than warn, because "remember to set it in
production" is the convention that already failed here once.
"""
from __future__ import annotations

import pytest

from app.config import DEV_JWT_SECRET, MIN_JWT_SECRET_LENGTH, Settings

DEV_DB = "postgresql+psycopg2://postgres:test@localhost:5434/surdev"  # pragma: allowlist secret
GOOD_SECRET = "s" * MIN_JWT_SECRET_LENGTH  # pragma: allowlist secret


def _settings(**kw):
    return Settings(database_url=DEV_DB, **kw)


def test_production_refuses_the_published_default_secret():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is still the development default"):
        _settings(environment="production", jwt_secret_key=DEV_JWT_SECRET)


def test_production_refuses_a_secret_short_enough_to_brute_force():
    with pytest.raises(RuntimeError, match="at least 32 are required"):
        _settings(environment="production", jwt_secret_key="s" * (MIN_JWT_SECRET_LENGTH - 1))


def test_production_accepts_a_real_secret():
    """The refusals must be about the value, not about production being
    unbootable."""
    s = _settings(environment="production", jwt_secret_key=GOOD_SECRET)
    assert s.jwt_secret_key == GOOD_SECRET


def test_production_refuses_wildcard_cors_because_credentials_are_allowed():
    with pytest.raises(RuntimeError, match="API_CORS_ORIGINS is"):
        _settings(environment="production", jwt_secret_key=GOOD_SECRET, api_cors_origins="*")


def test_production_accepts_a_real_origin_list():
    s = _settings(
        environment="production",
        jwt_secret_key=GOOD_SECRET,
        api_cors_origins="https://app.example.com,https://www.example.com",
    )
    assert "*" not in s.cors_origin_list


@pytest.mark.parametrize("env", ["development", "dev", "test", "staging", ""])
def test_dev_is_left_alone(env):
    """A local checkout must still start with zero configuration. Making
    developers set secrets to run tests is how the guard gets deleted."""
    s = _settings(environment=env, api_cors_origins="*")
    assert s.jwt_secret_key == DEV_JWT_SECRET


def test_the_default_and_the_guard_share_one_constant():
    """If the field default were spelled separately from the value the guard
    compares against, changing one would silently disarm the other."""
    assert Settings.model_fields["jwt_secret_key"].default is DEV_JWT_SECRET
