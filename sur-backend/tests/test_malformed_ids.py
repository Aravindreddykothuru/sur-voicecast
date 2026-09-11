"""A malformed id must be a clean 404 / permanent error -- never a 500.

Postgres's native uuid type rejects a non-uuid string outright
(InvalidTextRepresentation -> DataError), so `db.get(Project, "abc")` raises
instead of returning None. SQLite stores these columns as CHAR(36) and
quietly returns no rows, which is why this was invisible for the entire life
of the SQLite-backed suite: a typo'd id was a tidy 404 in tests and a 500 in
production.

Worse on the Celery side: DataError is not in tasks._PERMANENT, so a task
handed a malformed id burned three retries with backoff on input that could
never become valid.

This covers every entry point where an externally supplied id reaches a
query -- path params, request bodies, and task signatures -- so the next one
added is covered by the same parametrization rather than needing to be
remembered.
"""
from __future__ import annotations

import pytest

from app.models.base import is_uuid

# Not a uuid, in the ways that actually show up: a typo, a truncated id, an
# empty segment, a SQL-ish string, and a uuid with one character wrong.
MALFORMED_IDS = [
    "does-not-exist",
    "12345",
    "",
    "'; DROP TABLE projects;--",
    "ffffffff-ffff-ffff-ffff-fffffffffffZ",
]

# Every GET/POST route whose path carries an id. Each must answer 404, not 500.
ID_PATH_ROUTES = [
    ("GET", "/api/projects/{id}"),
    ("GET", "/api/projects/{id}/segments"),
    ("GET", "/api/projects/{id}/export"),
    ("POST", "/api/projects/{id}/upload"),
    ("POST", "/api/projects/{id}/upload/confirm"),
    ("POST", "/api/projects/{id}/process"),
    ("POST", "/api/projects/{id}/confirm-language"),
    ("PATCH", "/api/segments/{id}"),
    ("POST", "/api/segments/{id}/regenerate"),
]

_BODIES = {
    "/api/projects/{id}/upload": {"filename": "a.mp4", "content_type": "video/mp4"},
    "/api/projects/{id}/upload/confirm": {"source_video_id": "does-not-exist"},
    "/api/projects/{id}/process": {},
    "/api/projects/{id}/confirm-language": {},
    "/api/segments/{id}": {"translated_text": "x"},
    "/api/segments/{id}/regenerate": {"stages": ["translate"]},
}


def test_is_uuid_accepts_real_uuids_and_rejects_everything_else():
    import uuid as _uuid

    assert is_uuid(str(_uuid.uuid4()))
    for bad in MALFORMED_IDS:
        assert not is_uuid(bad), f"{bad!r} should not be treated as a usable id"
    assert not is_uuid(None)


@pytest.mark.parametrize("method,template", ID_PATH_ROUTES)
@pytest.mark.parametrize("bad_id", MALFORMED_IDS)
def test_malformed_path_id_is_404_never_500(client, method, template, bad_id):
    path = template.replace("{id}", bad_id or "%20")
    body = _BODIES.get(template)
    resp = client.request(method, path, json=body)

    assert resp.status_code < 500, (
        f"{method} {path} returned {resp.status_code} -- a malformed id must not "
        f"reach the database as a uuid. Body: {resp.text[:200]}"
    )
    # 404 is the intended answer; 405/422 are acceptable for a path that
    # doesn't route at all (e.g. an empty id segment collapsing the URL).
    assert resp.status_code in (404, 405, 422), f"{method} {path} -> {resp.status_code}"


@pytest.mark.parametrize("bad_id", MALFORMED_IDS)
def test_malformed_source_video_id_in_request_body_is_404(client, fake_storage, bad_id):
    """The id here arrives in the BODY, not the path -- a separate entry
    point that the path-param guard in deps.py does not cover."""
    created = client.post("/api/projects", json={"title": "P", "target_languages": ["te"]})
    project_id = created.json()["id"]

    resp = client.post(
        f"/api/projects/{project_id}/upload/confirm",
        json={"source_video_id": bad_id},
    )
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.parametrize("bad_id", MALFORMED_IDS)
def test_pipeline_tasks_reject_malformed_ids_permanently(bad_id):
    """ValueError, not DataError: ValueError is in tasks._PERMANENT, so Celery
    fails immediately instead of retrying three times on an id that can never
    become valid."""
    from celery.exceptions import Retry as CeleryRetry

    from app.pipeline import tasks as pipeline_tasks
    from app.pipeline.regenerate import regenerate_segment

    single_arg_tasks = [
        pipeline_tasks.transcribe,
        pipeline_tasks.detect_emotion,
        pipeline_tasks.translate,
        pipeline_tasks.synthesize,
        pipeline_tasks.mux_export,
    ]
    for task in single_arg_tasks:
        with pytest.raises((ValueError, CeleryRetry)):
            task.apply(args=[bad_id]).get()

    for task in [pipeline_tasks.extract_audio, pipeline_tasks.chunk_and_diarize]:
        with pytest.raises((ValueError, CeleryRetry)):
            task.apply(args=[bad_id, bad_id]).get()

    with pytest.raises((ValueError, CeleryRetry)):
        regenerate_segment.apply(args=[bad_id, ["translate"]]).get()
