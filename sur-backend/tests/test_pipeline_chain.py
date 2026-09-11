"""End-to-end pipeline test with every ML dependency mocked out: proves the
seven stages actually hand off to each other correctly (segments created,
statuses advance, an export lands with a QA report) without needing ffmpeg,
a GPU, or a real video file.
"""
from __future__ import annotations

from unittest.mock import patch

from celery.exceptions import Retry as CeleryRetry
from sqlalchemy import select

from app.db import session_scope
from app.models.export_job import ExportJob, ExportStatus
from app.models.project import Project, ProjectStatus
from app.models.segment import Segment, SegmentStatus
from app.models.source_video import SourceVideo, SourceVideoStatus
from app.models.user import User
from app.pipeline import tasks as pipeline_tasks


def _make_project_with_uploaded_video(fake_storage) -> tuple[str, str]:
    with session_scope() as db:
        user = User(email="dev@sur.local")
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, title="Test film", target_languages=["te"])
        db.add(project)
        db.flush()

        # Fake source video bytes -- ffmpeg calls are monkeypatched below so
        # the content never actually needs to be a real MP4.
        local_path = "/tmp/sur_test_source.mp4"
        with open(local_path, "wb") as f:
            f.write(b"not a real video, just bytes")

        video = SourceVideo(
            project_id=project.id,
            original_filename="movie.mp4",
            storage_key=f"projects/{project.id}/videos/src/movie.mp4",
            status=SourceVideoStatus.uploaded,
        )
        db.add(video)
        db.flush()
        fake_storage.upload_file(video.storage_key, local_path)
        return project.id, video.id


def test_full_pipeline_runs_end_to_end(fake_storage):
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda src, dst: open(dst, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 12000),
        patch("app.pipeline.tasks.ffmpeg_utils.mux_timeline", lambda video, placements, out: open(out, "wb").write(b"mp4")),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()
        pipeline_tasks.transcribe.apply(args=[project_id]).get()
        pipeline_tasks.detect_emotion.apply(args=[project_id]).get()
        pipeline_tasks.translate.apply(args=[project_id]).get()
        pipeline_tasks.synthesize.apply(args=[project_id]).get()
        pipeline_tasks.mux_export.apply(args=[project_id]).get()

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status == ProjectStatus.ready

        segments = db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all()
        assert len(segments) >= 3
        assert all(s.status == SegmentStatus.muxed for s in segments)
        assert all(s.translated_text and s.translated_text.startswith("[TE]") for s in segments)
        assert all(s.tts_audio_url for s in segments)

        export = db.execute(select(ExportJob).where(ExportJob.project_id == project_id)).scalar_one()
        assert export.status == ExportStatus.ready
        assert export.output_url
        assert export.qa_report["overall"]["segment_count"] == len(segments)


def test_pipeline_stage_failure_marks_project_failed(fake_storage):
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", side_effect=RuntimeError("ffmpeg exploded")):
        try:
            pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
            raise AssertionError("expected the task to raise")
        except (RuntimeError, CeleryRetry):
            # An ffmpeg blow-up is classed as transient, so autoretry_for wraps
            # it in Retry before re-raising; either surfacing is a failure from
            # the caller's point of view. What matters is the project state
            # asserted below.
            pass

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status == ProjectStatus.failed
        assert "ffmpeg exploded" in project.error_message


def test_chunk_and_diarize_is_idempotent(fake_storage):
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda src, dst: open(dst, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 12000),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()
        with session_scope() as db:
            first_count = len(db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all())

        # Re-running the stage (as a retry would) must not create duplicates.
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()
        with session_scope() as db:
            second_count = len(db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all())

    assert first_count == second_count


class _EmptyDiarization:
    """Stands in for a diarization provider whose VAD finds no speech turns --
    what pyannote returns for short/quiet single-speaker clips, and what
    silently stranded a real run in "processing" forever (chunk_and_diarize
    created 0 segments, transcribe early-returned, the chain ended)."""

    def chunk_and_diarize(self, audio_path: str):
        return []


class _OneLongTurnDiarization:
    """Real diarization can return a single uninterrupted monologue turn far
    longer than 30s -- CosyVoice2 then rejects it as a voice reference."""

    def __init__(self, span_ms: int):
        self._span = span_ms

    def chunk_and_diarize(self, audio_path: str):
        from app.providers.base import SpeakerChunk

        return [SpeakerChunk(start_ms=0, end_ms=self._span, speaker_tag="SPEAKER_00")]


def test_long_diarization_turn_is_split_below_the_tts_reference_cap(fake_storage):
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda src, dst: open(dst, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 41000),
        patch("app.pipeline.tasks.get_diarization_provider", lambda: _OneLongTurnDiarization(41000)),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()

    with session_scope() as db:
        segments = sorted(
            db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all(),
            key=lambda s: s.start_ms,
        )
        assert len(segments) >= 2, "a 41s turn must be split, not stored as one over-long segment"
        assert all((s.end_ms - s.start_ms) <= 30_000 for s in segments)
        assert segments[0].start_ms == 0 and segments[-1].end_ms == 41000
        for a, b in zip(segments, segments[1:]):
            assert a.end_ms == b.start_ms


def test_empty_diarization_falls_back_to_windowed_segments(fake_storage):
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda src, dst: open(dst, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 9000),
        patch("app.pipeline.tasks.get_diarization_provider", lambda: _EmptyDiarization()),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()

    with session_scope() as db:
        segments = db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all()
        assert len(segments) == 1, "empty diarization must fall back to >= 1 segment, not zero"
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 9000
        project = db.get(Project, project_id)
        assert project.status != ProjectStatus.failed


def test_empty_diarization_fallback_windows_stay_under_the_tts_reference_cap(fake_storage):
    """CosyVoice2 caps its voice-clone reference (each segment's own audio) at
    30s. A 57s WhatsApp clip fell back to one whole-file segment and then blew
    up in synthesize. The fallback must window the audio, not hand TTS a
    single over-long segment."""
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda src, dst: open(dst, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 56900),
        patch("app.pipeline.tasks.get_diarization_provider", lambda: _EmptyDiarization()),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()

    with session_scope() as db:
        segments = sorted(
            db.execute(select(Segment).where(Segment.project_id == project_id)).scalars().all(),
            key=lambda s: s.start_ms,
        )
        assert len(segments) >= 3
        assert all((s.end_ms - s.start_ms) <= 30_000 for s in segments), "a fallback window exceeds CosyVoice's 30s cap"
        assert segments[0].start_ms == 0
        assert segments[-1].end_ms == 56900
        # windows are contiguous, no gaps or overlaps
        for a, b in zip(segments, segments[1:]):
            assert a.end_ms == b.start_ms


def test_transcribe_with_zero_segments_fails_loudly_not_silently(fake_storage):
    """Defense in depth: if no segment exists at all, transcribe must fail
    visibly rather than complete and leave the run wedged in 'processing'."""
    project_id, _video_id = _make_project_with_uploaded_video(fake_storage)

    # Give the project an extracted audio key so transcribe gets past its
    # own preconditions and reaches the no-segments check.
    with session_scope() as db:
        video = db.execute(select(SourceVideo).where(SourceVideo.project_id == project_id)).scalar_one()
        video.audio_storage_key = f"projects/{project_id}/audio.wav"
        video.status = SourceVideoStatus.extracted

    try:
        pipeline_tasks.transcribe.apply(args=[project_id]).get()
        raise AssertionError("expected transcribe to raise on zero segments")
    except (ValueError, CeleryRetry):
        pass

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status == ProjectStatus.failed, f"expected failed, got {project.status}"
        assert "no segments" in (project.error_message or "")


def test_a_stale_error_is_cleared_once_a_later_stage_actually_succeeds(fake_storage):
    """A project that failed once, then succeeded on retry, must not keep
    showing the old (now-resolved) error_message -- confirmed live: a real
    Supabase project's transcribe stage hit a transient connection drop,
    auto-retried, and fully succeeded (all segments transcribed, status
    correctly advanced to awaiting_language_confirmation) but the UPDATE
    that would have cleared error_message from the earlier failed attempt
    never ran, leaving stale failure text on an otherwise-healthy project."""
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", side_effect=RuntimeError("transient blip")):
        try:
            pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
            raise AssertionError("expected the task to raise")
        except (RuntimeError, CeleryRetry):
            pass

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status == ProjectStatus.failed
        assert "transient blip" in project.error_message

    with patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", lambda src, dst: open(dst, "wb").write(b"wav")):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project.status != ProjectStatus.failed
        assert project.error_message is None, f"stale error survived a successful retry: {project.error_message!r}"
        assert project.error_is_permanent is None


def test_a_retried_stage_stores_its_own_error_not_the_previous_attempts(fake_storage):
    """"Cleared on every stage transition, not only on success" -- the
    retry half of that requirement.

    NOTE on what is NOT asserted here, deliberately: the clear itself
    happens in _set_stage(), which runs inside the stage's own
    `with session_scope()` block, and the stage's work happens in that same
    uncommitted transaction. So "error_message is already None while the
    retry is still running" is not observable from another connection --
    not in this test, and not in production either, because that
    intermediate state is never committed. Asserting it would be asserting
    a fiction. What IS observable, and what actually matters, is the
    committed end state on both paths: a succeeding retry clears the old
    error (covered by the test above), and a re-failing retry stores ITS
    error rather than preserving the stale one (covered here)."""
    project_id, video_id = _make_project_with_uploaded_video(fake_storage)

    with patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", side_effect=RuntimeError("first failure")):
        try:
            pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        except (RuntimeError, CeleryRetry):
            pass

    with session_scope() as db:
        assert "first failure" in db.get(Project, project_id).error_message

    with patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav", side_effect=RuntimeError("second failure")):
        try:
            pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        except (RuntimeError, CeleryRetry):
            pass

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert "second failure" in project.error_message
        assert "first failure" not in project.error_message, (
            "the retry kept the previous attempt's error instead of replacing it"
        )
