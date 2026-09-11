"""POST /api/auth/signup and /api/auth/login -- real, password-verified
identity. See app/core/security.py for hashing/token issuance and the
layered get_current_user that accepts either the resulting bearer token or
the pre-existing X-User-Email dev stub.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing is not None and existing.password_hash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    if existing is not None:
        # A row created by the old X-User-Email dev stub, never signed up
        # for real -- claim it rather than fail on a technicality the user
        # has no way to see or fix.
        user = existing
        user.password_hash = hash_password(body.password)
        if body.name:
            user.name = body.name
    else:
        user = User(email=body.email, name=body.name, password_hash=hash_password(body.password))
        db.add(user)

    db.commit()
    db.refresh(user)
    return AuthResponse(token=create_access_token(user.id), user=user)  # type: ignore[arg-type]


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    # Same generic message whether the email doesn't exist, has no password
    # yet (dev-stub-only row), or the password is simply wrong -- telling
    # them apart lets an attacker enumerate which emails have accounts.
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    if user is None or user.password_hash is None:
        raise invalid
    if not verify_password(body.password, user.password_hash):
        raise invalid

    return AuthResponse(token=create_access_token(user.id), user=user)  # type: ignore[arg-type]
