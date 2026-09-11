"""The pipeline must not spend the expensive half on a mis-detected language.

TTS runs minutes per sentence on CPU. Running straight through on a wrong
auto-detect produces a dub in the wrong language and wastes all of it, so the
run parks after ASR until a human confirms or corrects. See CONTRACTS.md #5.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models.project import Project, ProjectStatus
from app.models.segment import Segment, SegmentStatus
from app.models.source_video import SourceVideo, SourceVideoStatus
from app.models.user import User
from app.pipeline import tasks as pipeline_tasks


def _seed(fake_storage, *, review_language: bool = True):
    import pathlib
    import tempfile

    with session_scope() as db:
        user = User(email="dev@sur.local")  # must match DEV_DEFAULT_USER_EMAIL for the stubbed auth
        db.add(user)
        db.flush()
        project = Project(
            user_id=user.id, title="Gate", target_languages=["te"], review_language=review_language
        )
        db.add(project)
        db.flush()
        video = SourceVideo(
            project_id=project.id, original_filename="m.mp4", storage_key="src.mp4",
            status=SourceVideoStatus.uploaded,
        )
        db.add(video)
        db.flush()
        ids = (project.id, video.id)

    local = pathlib.Path(tempfile.mkdtemp()) / "src.mp4"
    local.write_bytes(b"fake")
    fake_storage.upload_file("src.mp4", str(local))
    return ids


import contextlib


@contextlib.contextmanager
def _fake_slice(audio_path, start_ms, end_ms):
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(b"wav")
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


@contextlib.contextmanager
def _no_real_media():
    """These tests are about the gate, not ffmpeg -- the media calls are
    exercised for real in tests/test_timeline_accuracy.py."""
    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda s_, d: open(d, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 12000),
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_slice", _fake_slice),
        patch("app.pipeline.tasks.ffmpeg_utils.mux_timeline",
              lambda v, placements, out: open(out, "wb").write(b"mp4")),
    ):
        yield


def _run_through_asr(project_id, video_id):
    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda s_, d: open(d, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 12000),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()
        pipeline_tasks.transcribe.apply(args=[project_id]).get()


def test_pipeline_parks_after_asr_for_confirmation(fake_storage):
    project_id, video_id = _seed(fake_storage, review_language=True)
    _run_through_asr(project_id, video_id)

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status == ProjectStatus.awaiting_language_confirmation, (
            "run continued into the expensive stages without confirming the language"
        )


def test_pipeline_runs_straight_through_when_review_is_off(fake_storage):
    project_id, video_id = _seed(fake_storage, review_language=False)
    _run_through_asr(project_id, video_id)

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status != ProjectStatus.awaiting_language_confirmation


def test_detected_language_and_confidence_are_persisted(fake_storage):
    """The UI can only show a wrong auto-detect if ASR's answer was stored."""
    project_id, video_id = _seed(fake_storage)
    _run_through_asr(project_id, video_id)

    with session_scope() as db:
        segments = db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all()
        assert segments
        for seg in segments:
            assert seg.detected_language, "ASR result recorded no language"
            assert seg.detected_language_confidence is not None


def test_confirm_language_accepts_detection_and_resumes(client, fake_storage):
    project_id, video_id = _seed(fake_storage)
    _run_through_asr(project_id, video_id)

    with _no_real_media():
        resp = client.post(f"/api/projects/{project_id}/confirm-language", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] != "awaiting_language_confirmation"


def test_confirm_language_override_retranscribes_with_chosen_language(client, fake_storage):
    project_id, video_id = _seed(fake_storage)
    _run_through_asr(project_id, video_id)

    with session_scope() as db:
        before = db.execute(
            select(Segment.detected_language).where(Segment.project_id == project_id).limit(1)
        ).scalar_one()
    assert before == "en"

    with _no_real_media():
        resp = client.post(f"/api/projects/{project_id}/confirm-language", json={"source_language": "hi"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["source_language"] == "hi"

    with session_scope() as db:
        after = db.execute(
            select(Segment.detected_language).where(Segment.project_id == project_id).limit(1)
        ).scalar_one()
    assert after == "hi", "override did not actually re-run transcription"


def test_confirm_language_rejects_a_project_not_at_the_gate(client, fake_storage):
    """A 409 with the real status, not a silent no-op."""
    project_id, _ = _seed(fake_storage)
    resp = client.post(f"/api/projects/{project_id}/confirm-language", json={})
    assert resp.status_code == 409
    assert "not awaiting language confirmation" in resp.json()["detail"]
