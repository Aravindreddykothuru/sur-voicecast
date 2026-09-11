"""Real signup/login: hashed passwords, generic error messages that don't
leak whether an email exists, and a bearer token that authenticates the
same routes X-User-Email always has. See app/core/security.py.
"""
from __future__ import annotations


def test_signup_then_login_round_trip(client):
    r = client.post("/api/auth/signup", json={"email": "new@x.com", "password": "correcthorse", "name": "New User"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "new@x.com"
    assert body["user"]["name"] == "New User"
    assert body["token"]

    r2 = client.post("/api/auth/login", json={"email": "new@x.com", "password": "correcthorse"})
    assert r2.status_code == 200
    assert r2.json()["user"]["email"] == "new@x.com"


def test_signup_rejects_duplicate_email(client):
    client.post("/api/auth/signup", json={"email": "dup@x.com", "password": "correcthorse"})
    r = client.post("/api/auth/signup", json={"email": "dup@x.com", "password": "anotherpassword"})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_signup_can_claim_a_dev_stub_created_row(client):
    """A user row created by the old X-User-Email dev stub (no password) has
    never actually signed up -- signing up with that email must succeed and
    set a real password, not be blocked as a duplicate."""
    client.get("/api/projects", headers={"X-User-Email": "stub@x.com"})  # auto-creates the row, no password

    r = client.post("/api/auth/signup", json={"email": "stub@x.com", "password": "correcthorse"})
    assert r.status_code == 201

    r2 = client.post("/api/auth/login", json={"email": "stub@x.com", "password": "correcthorse"})
    assert r2.status_code == 200


def test_signup_rejects_short_password(client):
    r = client.post("/api/auth/signup", json={"email": "short@x.com", "password": "1234567"})
    assert r.status_code == 422


def test_signup_rejects_malformed_email(client):
    r = client.post("/api/auth/signup", json={"email": "not-an-email", "password": "correcthorse"})
    assert r.status_code == 422


def test_login_wrong_password_is_rejected(client):
    client.post("/api/auth/signup", json={"email": "wrongpw@x.com", "password": "correcthorse"})
    r = client.post("/api/auth/login", json={"email": "wrongpw@x.com", "password": "notthepassword"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password."


def test_login_nonexistent_email_gives_the_same_message_as_wrong_password(client):
    """Different wording for "no such account" vs "wrong password" lets an
    attacker enumerate which emails have accounts -- both must read
    identically."""
    client.post("/api/auth/signup", json={"email": "exists@x.com", "password": "correcthorse"})

    r_missing = client.post("/api/auth/login", json={"email": "nosuchaccount@x.com", "password": "whatever1"})
    r_wrong = client.post("/api/auth/login", json={"email": "exists@x.com", "password": "wrongpassword"})

    assert r_missing.status_code == r_wrong.status_code == 401
    assert r_missing.json()["detail"] == r_wrong.json()["detail"] == "Incorrect email or password."


def test_login_rejects_a_dev_stub_only_account_with_no_password(client):
    client.get("/api/projects", headers={"X-User-Email": "neverclaimed@x.com"})
    r = client.post("/api/auth/login", json={"email": "neverclaimed@x.com", "password": "anything1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password."


def test_bearer_token_authenticates_and_scopes_to_the_right_user(client):
    r = client.post("/api/auth/signup", json={"email": "bearer@x.com", "password": "correcthorse"})
    token = r.json()["token"]

    created = client.post(
        "/api/projects",
        json={"title": "My bearer-auth project", "target_languages": ["te"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201

    listed = client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    titles = [p["title"] for p in listed.json()]
    assert "My bearer-auth project" in titles

    # A DIFFERENT user's token must not see it (project isolation still holds
    # for bearer-token identity, same as it already does for X-User-Email).
    other = client.post("/api/auth/signup", json={"email": "other-bearer@x.com", "password": "correcthorse"})
    other_token = other.json()["token"]
    other_listed = client.get("/api/projects", headers={"Authorization": f"Bearer {other_token}"})
    assert "My bearer-auth project" not in [p["title"] for p in other_listed.json()]


def test_invalid_bearer_token_is_rejected(client):
    r = client.get("/api/projects", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_x_user_email_still_works_when_no_bearer_token_present(client):
    """Every pre-auth route and test must keep working unchanged."""
    r = client.get("/api/projects", headers={"X-User-Email": "legacy@x.com"})
    assert r.status_code == 200
