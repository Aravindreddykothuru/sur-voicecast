from __future__ import annotations


def test_create_and_get_project(client):
    resp = client.post("/api/projects", json={"title": "My Film", "target_languages": ["te"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "My Film"
    assert body["status"] == "draft"

    resp2 = client.get(f"/api/projects/{body['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == body["id"]


def test_list_projects_scoped_to_user(client):
    client.post("/api/projects", json={"title": "A", "target_languages": ["te"]}, headers={"X-User-Email": "a@x.com"})
    client.post("/api/projects", json={"title": "B", "target_languages": ["hi"]}, headers={"X-User-Email": "b@x.com"})

    resp = client.get("/api/projects", headers={"X-User-Email": "a@x.com"})
    titles = [p["title"] for p in resp.json()]
    assert titles == ["A"]


def test_get_missing_project_is_404(client):
    resp = client.get("/api/projects/does-not-exist")
    assert resp.status_code == 404


def test_upload_url_issued_and_confirmable(client, fake_storage):
    project = client.post("/api/projects", json={"title": "F", "target_languages": ["te"]}).json()

    upload = client.post(
        f"/api/projects/{project['id']}/upload", json={"filename": "movie.mp4", "content_type": "video/mp4"}
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["storage_key"].endswith("movie.mp4")

    # /upload/confirm checks the object's real size in storage (never the
    # client's say-so) -- simulate the presigned PUT actually completing
    # before confirming, same as a real client would have.
    import tempfile, pathlib
    local = pathlib.Path(tempfile.mkdtemp()) / "movie.mp4"
    local.write_bytes(b"fake-mp4-bytes")
    fake_storage.upload_file(body["storage_key"], str(local))

    confirm = client.post(
        f"/api/projects/{project['id']}/upload/confirm",
        json={"source_video_id": body["source_video_id"], "duration_ms": 60000},
    )
    assert confirm.status_code == 200


def test_process_requires_uploaded_video(client):
    project = client.post("/api/projects", json={"title": "F", "target_languages": ["te"]}).json()
    resp = client.post(f"/api/projects/{project['id']}/process", json={})
    assert resp.status_code == 400


def test_upload_rejects_unsupported_content_type(client):
    """The client's declared content_type is checked against
    Settings.accepted_video_format_list before a storage key is even
    allocated -- offering a format the pipeline can't process is worse than
    refusing it up front. See CONTRACTS.md #5."""
    project = client.post("/api/projects", json={"title": "F", "target_languages": ["te"]}).json()

    resp = client.post(
        f"/api/projects/{project['id']}/upload",
        json={"filename": "clip.exe", "content_type": "application/x-msdownload"},
    )
    assert resp.status_code == 400
    assert "Unsupported content type" in resp.json()["detail"]


def test_confirm_rejects_upload_exceeding_max_size(client, fake_storage, monkeypatch):
    """The regression this guards against: a client could previously call
    /upload then /upload/confirm with no server-side size check at all, so an
    oversized file would sail through to the pipeline and fail (or hang)
    deep inside extract_audio instead of being refused immediately. Only the
    storage backend's own get_size() is trusted, never body.duration_ms or
    any other client-supplied number."""
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")  # 0MB: anything at all is "too large"
    get_settings.cache_clear()

    project = client.post("/api/projects", json={"title": "F", "target_languages": ["te"]}).json()
    upload = client.post(
        f"/api/projects/{project['id']}/upload", json={"filename": "movie.mp4", "content_type": "video/mp4"}
    ).json()

    import tempfile, pathlib
    local = pathlib.Path(tempfile.mkdtemp()) / "movie.mp4"
    local.write_bytes(b"x" * 1024)
    fake_storage.upload_file(upload["storage_key"], str(local))

    confirm = client.post(
        f"/api/projects/{project['id']}/upload/confirm",
        json={"source_video_id": upload["source_video_id"]},
    )
    assert confirm.status_code == 413
    assert not fake_storage.exists(upload["storage_key"]), "oversized upload should be deleted, not kept"

    get_settings.cache_clear()
