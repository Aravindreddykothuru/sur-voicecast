"""User A must not be able to reach user B's data through any entry point.

is_uuid answered "is this id well-formed". It never answered "does this
caller own this row". Those are different questions, and only the first one
had been asked -- the WebSocket route asked neither, so anyone who knew or
guessed a project id could stream that project's transcripts, detected
language and error messages.

Parametrized across every id-bearing route so a new one is covered by the
same table rather than by someone remembering to add a case.
"""
from __future__ import annotations

import pytest

A = {"X-User-Email": "alice@example.com"}
B = {"X-User-Email": "bob@example.com"}


@pytest.fixture
def bobs_project(client, fake_storage):
    """A project owned by Bob, with an uploaded video and a segment, so every
    route under test has something real to refuse Alice access to."""
    resp = client.post("/api/projects", json={"title": "Bob's film", "target_languages": ["te"]}, headers=B)
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]

    up = client.post(
        f"/api/projects/{project_id}/upload",
        json={"filename": "b.mp4", "content_type": "video/mp4"},
        headers=B,
    )
    assert up.status_code == 200, up.text
    return {"project_id": project_id, "source_video_id": up.json()["source_video_id"]}


# (method, path template, body) for everything that takes a project id.
PROJECT_ROUTES = [
    ("GET", "/api/projects/{pid}", None),
    ("GET", "/api/projects/{pid}/segments", None),
    ("GET", "/api/projects/{pid}/export", None),
    ("POST", "/api/projects/{pid}/upload", {"filename": "a.mp4", "content_type": "video/mp4"}),
    ("POST", "/api/projects/{pid}/upload/confirm", {"source_video_id": "00000000-0000-0000-0000-000000000000"}),
    ("POST", "/api/projects/{pid}/process", {}),
    ("POST", "/api/projects/{pid}/confirm-language", {}),
]


@pytest.mark.parametrize("method,template,body", PROJECT_ROUTES)
def test_alice_cannot_touch_bobs_project(client, bobs_project, method, template, body):
    path = template.format(pid=bobs_project["project_id"])
    resp = client.request(method, path, json=body, headers=A)
    assert resp.status_code == 404, (
        f"{method} {path} as Alice returned {resp.status_code}; Bob's project must be "
        f"invisible to her. Body: {resp.text[:200]}"
    )


def test_bob_can_reach_his_own_project(client, bobs_project):
    """The refusals above have to be about ownership, not a blanket 404."""
    resp = client.get(f"/api/projects/{bobs_project['project_id']}", headers=B)
    assert resp.status_code == 200, resp.text


def test_alices_project_list_never_contains_bobs(client, bobs_project):
    client.post("/api/projects", json={"title": "Alice's", "target_languages": ["hi"]}, headers=A)
    titles = [p["title"] for p in client.get("/api/projects", headers=A).json()]
    assert "Bob's film" not in titles
    assert titles == ["Alice's"]


def _ws_is_rejected(client, url) -> bool:
    """True if the server refused the handshake.

    Deliberately never calls receive_text() on the success path: when Redis
    is reachable the server subscribes and then stays silent until a real
    pipeline event arrives, so a receive would block forever. Rejection is
    observable from the handshake alone.
    """
    from starlette.websockets import WebSocketDisconnect as WSDisconnect

    try:
        with client.websocket_connect(url):
            return False
    except WSDisconnect:
        return True


def test_alice_cannot_subscribe_to_bobs_websocket(client, bobs_project):
    """The gap this file was written for: the WS route had no ownership check
    at all, so a project id was the only thing between an attacker and
    another user's live transcript stream."""
    pid = bobs_project["project_id"]
    assert _ws_is_rejected(client, f"/ws/projects/{pid}?user_email=alice@example.com"), (
        "Alice was allowed to subscribe to Bob's project events"
    )


def test_anonymous_cannot_subscribe_at_all(client, bobs_project):
    pid = bobs_project["project_id"]
    assert _ws_is_rejected(client, f"/ws/projects/{pid}"), (
        "an unauthenticated client was allowed to subscribe"
    )


def test_bob_can_subscribe_to_his_own_websocket(client, bobs_project):
    """The refusals above must be about ownership, not the socket being
    broken for everyone."""
    pid = bobs_project["project_id"]
    assert not _ws_is_rejected(client, f"/ws/projects/{pid}?user_email=bob@example.com"), (
        "the owner was refused his own project's events"
    )
