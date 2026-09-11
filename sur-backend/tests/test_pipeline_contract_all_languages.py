"""Runs the real orchestration end-to-end for EVERY supported language.

CONTRACTS.md invariant #2. The original bug was not that translation was
wrong, it was that 5 languages the UI offered had never been executed even
once. Models are mocked; the orchestration, status transitions, language
resolution and export are real, so an unmapped language surfaces here as a
CI failure rather than in production.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.capabilities import SUPPORTED_LANGUAGES
from app.db import session_scope
from app.models.export_job import ExportJob, ExportStatus
from app.models.project import Project, ProjectStatus
from app.models.segment import Segment, SegmentStatus
from app.models.source_video import SourceVideo, SourceVideoStatus
from app.models.user import User
from app.pipeline import tasks as pipeline_tasks


def _make_project(fake_storage, target_lang: str) -> tuple[str, str]:
    with session_scope() as db:
        user = User(email=f"dev+{target_lang}@sur.local")
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, title=f"P-{target_lang}", target_languages=[target_lang])
        db.add(project)
        db.flush()
        video = SourceVideo(
            project_id=project.id,
            original_filename="m.mp4",
            storage_key=f"src/{target_lang}.mp4",
            status=SourceVideoStatus.uploaded,
        )
        db.add(video)
        db.flush()
        ids = (project.id, video.id)

    import tempfile, pathlib
    local = pathlib.Path(tempfile.mkdtemp()) / "src.mp4"
    local.write_bytes(b"fake-mp4")
    fake_storage.upload_file(f"src/{target_lang}.mp4", str(local))
    return ids


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES, ids=lambda l: l.code)
def test_full_pipeline_succeeds_for_every_supported_language(fake_storage, lang):
    project_id, video_id = _make_project(fake_storage, lang.code)

    with (
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_wav",
              lambda src, dst: open(dst, "wb").write(b"wav")),
        patch("app.pipeline.tasks.ffmpeg_utils.probe_duration_ms", lambda p: 12000),
        patch("app.pipeline.tasks.ffmpeg_utils.extract_audio_slice", _fake_slice),
        patch("app.pipeline.tasks.ffmpeg_utils.mux_timeline",
              lambda video, placements, out: open(out, "wb").write(b"mp4")),
    ):
        pipeline_tasks.extract_audio.apply(args=[project_id, video_id]).get()
        pipeline_tasks.chunk_and_diarize.apply(args=[project_id, video_id]).get()
        pipeline_tasks.transcribe.apply(args=[project_id]).get()
        pipeline_tasks.detect_emotion.apply(args=[project_id]).get()
        # The stage that used to raise ValueError for 5 of the 12 languages:
        pipeline_tasks.translate.apply(args=[project_id]).get()
        pipeline_tasks.synthesize.apply(args=[project_id]).get()
        pipeline_tasks.mux_export.apply(args=[project_id]).get()

    with session_scope() as db:
        project = db.get(Project, project_id)
        assert project is not None
        assert project.status == ProjectStatus.ready, (
            f"{lang.code} ({lang.name}) failed: {project.error_message}"
        )
        assert project.error_message is None

        segments = db.execute(
            select(Segment).where(Segment.project_id == project_id)
        ).scalars().all()
        assert segments, f"{lang.code}: no segments produced"
        assert all(s.status == SegmentStatus.muxed for s in segments)
        assert all(s.translated_text for s in segments), f"{lang.code}: untranslated segments"

        export = db.execute(
            select(ExportJob).where(ExportJob.project_id == project_id)
        ).scalar_one()
        assert export.status == ExportStatus.ready


import contextlib


@contextlib.contextmanager
def _fake_slice(audio_path, start_ms, end_ms):
    """Stands in for the ffmpeg slice so the synthesize stage's voice-reference
    lookup works without real media."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(b"wav")
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


# ---------------------------------------------------------------------------
# Regression: ASR detected "zh" at 98% confidence live, and translation
# silently ran it through the English->Indic model anyway, producing a
# confident but wrong Telugu sentence with no error anywhere. See
# CONTRACTS.md #3 and #5.
# ---------------------------------------------------------------------------
from app.capabilities import SOURCE_LANGUAGES, require_source_language
from app.pipeline.tasks import _project_source_language


def test_unsupported_detected_language_is_refused_not_guessed():
    """The exact bug: a source language the translation provider has no path
    for must raise, not be silently treated as English."""
    with pytest.raises(ValueError, match="Unsupported source language 'zh'"):
        require_source_language("zh")


def test_source_language_resolution_prefers_confirmed_over_detected():
    class FakeProject:
        id = "p1"
        source_language = "hi"

    class FakeSegment:
        detected_language = "en"

    assert _project_source_language(FakeProject(), [FakeSegment()]) == "hi"


def test_source_language_resolution_falls_back_to_asr_majority_vote():
    class FakeProject:
        id = "p1"
        source_language = None

    class FakeSegment:
        def __init__(self, lang):
            self.detected_language = lang

    segments = [FakeSegment("hi"), FakeSegment("hi"), FakeSegment("en")]
    assert _project_source_language(FakeProject(), segments) == "hi"


def test_source_language_resolution_raises_rather_than_defaulting_to_english():
    """CONTRACTS.md #3: no silent defaults. A project with no confirmed
    language and no ASR detection anywhere must fail, not assume English."""
    class FakeProject:
        id = "p1"
        source_language = None

    class FakeSegment:
        detected_language = None

    with pytest.raises(ValueError, match="cannot translate without guessing"):
        _project_source_language(FakeProject(), [FakeSegment()])


@pytest.mark.parametrize("lang", SOURCE_LANGUAGES, ids=lambda l: l.code)
def test_every_supported_source_language_resolves_a_real_direction(lang):
    """Every advertised source language must map to one of IndicTrans2's three
    real checkpoints -- not silently fall through to en-indic regardless."""
    from app.providers.translation.indictrans2_provider import IndicTrans2Provider

    provider = IndicTrans2Provider.__new__(IndicTrans2Provider)  # skip __init__ (no weights needed)
    direction, model_name = provider._direction_for(lang.code, "te")
    assert direction in ("en-indic", "indic-en", "indic-indic")
    assert model_name

    if lang.code == "en":
        assert direction == "en-indic"
    else:
        # target "te" is Indic and lang.code != "en" -> must be indic-indic,
        # never silently en-indic (which is what the original bug did).
        assert direction == "indic-indic"


# ---------------------------------------------------------------------------
# The gap above (test_every_supported_source_language_resolves_a_real_direction)
# only proves _direction_for() is wired correctly in isolation -- it does not
# run the translate stage itself. Proven empirically: re-injecting the exact
# original bug (translate_segment(seg, target_lang, "en") hardcoded, ignoring
# the resolved source_lang) into app/pipeline/tasks.py and re-running this
# whole file still passed 29/29, because
# test_full_pipeline_succeeds_for_every_supported_language uses
# MockTranslationProvider, which accepts any src_lang without checking it.
# This test closes that gap by spying on the provider call itself, so a
# hardcoded/wrong source_lang at ANY call site fails here regardless of
# whether the provider validates or even looks at it.
# ---------------------------------------------------------------------------
class _SpyTranslationProvider:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []  # (text, target_lang, src_lang)

    def translate(self, text, target_lang, src_lang="en"):
        self.calls.append((text, target_lang, src_lang))
        from app.providers.base import TranslationResult

        return TranslationResult(text=f"[{target_lang}] {text}", src_lang=src_lang, target_lang=target_lang)


def _make_project_with_segments(fake_storage, source_lang: str, target_lang: str, n_segments: int = 3):
    with session_scope() as db:
        user = User(email=f"dev+srcspy-{source_lang}@sur.local")
        db.add(user)
        db.flush()
        project = Project(
            user_id=user.id,
            title=f"P-src-{source_lang}",
            target_languages=[target_lang],
            source_language=source_lang,  # confirmed -- must NOT be overridden by any hardcoded default
        )
        db.add(project)
        db.flush()
        video = SourceVideo(
            project_id=project.id,
            original_filename="m.mp4",
            storage_key=f"src/srcspy-{source_lang}.mp4",
            status=SourceVideoStatus.uploaded,
        )
        db.add(video)
        db.flush()

        for i in range(n_segments):
            db.add(Segment(
                project_id=project.id,
                source_video_id=video.id,
                index=i,
                start_ms=i * 1000,
                end_ms=(i + 1) * 1000,
                source_text=f"segment {i}",
                status=SegmentStatus.emotion_detected,
            ))
        project_id = project.id

    import tempfile, pathlib
    local = pathlib.Path(tempfile.mkdtemp()) / "src.mp4"
    local.write_bytes(b"fake-mp4")
    fake_storage.upload_file(f"src/srcspy-{source_lang}.mp4", str(local))
    return project_id


def test_translate_stage_calls_provider_with_the_projects_resolved_source_language(fake_storage):
    """The exact regression: confirm a non-English source, run the real
    `translate` Celery task, and assert the provider was actually called with
    THAT source language for every segment -- not "en", whatever the mock
    would silently tolerate. A hardcoded src_lang at the translate_segment or
    translate() call site fails this immediately."""
    source_lang, target_lang = "hi", "en"
    project_id = _make_project_with_segments(fake_storage, source_lang, target_lang)

    spy = _SpyTranslationProvider()
    with patch("app.pipeline.tasks.get_translation_provider", lambda: spy):
        pipeline_tasks.translate.apply(args=[project_id]).get()

    assert spy.calls, "translate stage never called the translation provider"
    assert len(spy.calls) == 3
    for _text, called_target, called_src in spy.calls:
        assert called_target == target_lang
        assert called_src == source_lang, (
            f"provider was called with src_lang={called_src!r}, expected "
            f"{source_lang!r} (the project's confirmed source_language) -- "
            "this is the exact bug where a detected/confirmed non-English "
            "source was silently translated as if it were English."
        )

    with session_scope() as db:
        segments = db.execute(
            select(Segment).where(Segment.project_id == project_id)
        ).scalars().all()
        assert all(s.status == SegmentStatus.translated for s in segments)
        assert all(s.translated_text for s in segments)
