"""Password hashing, JWT issuance/verification, and request identity.

Real auth lives here now (see /api/auth/signup and /api/auth/login in
app/api/routes_auth.py): bcrypt-hashed passwords, a signed JWT handed back
on success. `get_current_user` prefers a valid bearer token -- the only
thing an attacker can't forge without the JWT secret -- and falls back to
the old X-User-Email dev stub only when no token is presented, so every
existing route, test, and the pre-auth dev flow keep working unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.user import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/legacy hash -- never let a verification error read as a
        # successful login.
        return False


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Returns the user id, or None for any invalid/expired/malformed token
    -- never raises, so callers can treat "no token" and "bad token" the
    same way (fall back or reject, their choice)."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> User:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        user_id = decode_access_token(token)
        if user_id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session. Please log in again.")
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session. Please log in again.")
        return user

    # Dev stub: no route or test that predates real auth needs to change.
    # Off in production, where it would be an unauthenticated takeover path
    # -- a header alone identifies (and silently creates) any account.
    settings = get_settings()
    if not settings.dev_email_auth_enabled:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )
    email = (x_user_email or settings.dev_default_user_email).strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
