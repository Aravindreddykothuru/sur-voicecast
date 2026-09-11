"""One Celery task per pipeline stage (PRD section 07).

Every task:
  * is idempotent -- re-running it re-derives state from what's already in
    Postgres rather than assuming a clean slate, so a retried task never
    double-creates rows or double-charges a GPU render;
  * only ever touches models/providers/storage -- never a model library
    directly (see app/providers/base.py's docstring for why);
  * emits stage_started/stage_progress/stage_completed around its work and
    error on failure, over the same EventBus the WebSocket gateway reads;
  * binds project_id (and segment_id where relevant) into the logging
    context so every log line for a run is greppable by project_id.

`app/pipeline/chain.py` wires these into the Celery chain that /process
kicks off. `app/pipeline/regenerate.py` calls the per-segment helpers here
directly for the single-segment /regenerate endpoint, without re-running
extract/diarize/transcribe.
"""
from __future__ import annotations

import logging
import shutil
import tempfile

from sqlalchemy import select

from app.celery_app import celery_app
from app.config import get_settings
from app.logging_conf import bind_context, clear_context
from app.models.export_job import ExportJob, ExportStatus
from app.models.project import Project, ProjectStatus
from app.models.segment import EmotionLabel, Segment, SegmentStatus
from app.models.source_video import SourceVideo, SourceVideoStatus
from app.models.speaker import Speaker
from app.pipeline import ffmpeg_utils
from app.pipeline.events import (
    emit_error,
    emit_segment_ready,
    emit_stage_completed,
    emit_stage_progress,
    emit_stage_started,
)
from app.models.base import is_uuid
from app.providers.base import EmotionResult, SpeakerChunk, SynthesisRequest
from app.providers.registry import (
    get_asr_provider,
    get_diarization_provider,
    get_emotion_provider,
    get_translation_provider,
    get_tts_provider,
)
from app.db import session_scope
from app.storage import get_storage

logger = logging.getLogger(__name__)

_RETRYABLE = (Exception,)

# Permanent failures: a missing project/segment/audio row, or an unsupported
# target language, will fail exactly the same way on every attempt, so
# retrying them three times with backoff only delays the error the operator
# needs to see and holds a worker slot while doing it. Everything else
# (network blips, S3 timeouts, a flaky ffmpeg subprocess) stays retryable.
_PERMANENT = (ValueError, LookupError, TypeError)


def _target_lang(project: Project) -> str:
    return project.target_languages[0] if project.target_languages else get_settings().default_target_language


def _mark_project_failed(project_id: str, stage: str, exc: Exception) -> None:
    with session_scope() as db:
        # Guard first: this runs inside the exception handler, so a DataError
        # from a malformed id would replace the real failure with a confusing
        # one and lose the original error entirely.
        project = db.get(Project, project_id) if is_uuid(project_id) else None
        if project:
            project.status = ProjectStatus.failed
            project.error_message = f"{stage}: {exc}"
            project.error_is_permanent = isinstance(exc, _PERMANENT)
    emit_error(project_id, stage, str(exc), permanent=isinstance(exc, _PERMANENT))


def _set_stage(db, project: Project, stage: str) -> None:
    project.current_stage = stage
    if project.status not in (ProjectStatus.processing,):
        project.status = ProjectStatus.processing
    # A stage only starts once the previous one succeeded, so any stored
    # error is necessarily resolved by now -- leaving it would let a stale,
    # already-fixed failure keep showing up in anything that reads
    # error_message without also checking status == failed.
    project.error_message = None
    project.error_is_permanent = None


def _require_project(db, project_id: str) -> Project:
    """Fail loudly and legibly if the project vanished mid-pipeline, rather
    than letting every stage trip over `NoneType has no attribute ...`."""
    # ValueError, not DataError: a malformed id can never become valid, and
    # ValueError is in _PERMANENT so Celery won't burn retries on it.
    project = db.get(Project, project_id) if is_uuid(project_id) else None
    if project is None:
        raise ValueError(f"project {project_id} not found")
    return project


def _require_audio_key(db, source_video_id: str) -> str:
    """Returns the extracted-audio storage key, or fails with a clear message."""
    video = db.get(SourceVideo, source_video_id) if is_uuid(source_video_id) else None
    if video is None:
        raise ValueError(f"source video {source_video_id} not found")
    if not video.audio_storage_key:
        raise ValueError(f"source video {source_video_id} has no extracted audio")
    return video.audio_storage_key


# ---------------------------------------------------------------------------
# Stage 1: extract_audio
# ---------------------------------------------------------------------------
@celery_app.task(bind=True, name="app.pipeline.tasks.extract_audio", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def extract_audio(self, project_id: str, source_video_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "extract_audio"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = db.get(Project, project_id) if is_uuid(project_id) else None
            video = db.get(SourceVideo, source_video_id) if is_uuid(source_video_id) else None
            if project is None or video is None:
                raise ValueError("project or source video not found")
            _set_stage(db, project, stage)

            if video.audio_storage_key and video.status == SourceVideoStatus.extracted:
                logger.info("extract_audio: already extracted, skipping (idempotent)")
                emit_stage_completed(project_id, stage)
                return project_id

            storage = get_storage()
            with tempfile.TemporaryDirectory() as tmp:
                video_path = f"{tmp}/source.mp4"
                audio_path = f"{tmp}/audio.wav"
                storage.download_file(video.storage_key, video_path)
                ffmpeg_utils.extract_audio_wav(video_path, audio_path)

                duration_ms = ffmpeg_utils.probe_duration_ms(video_path)
                audio_key = f"projects/{project_id}/videos/{source_video_id}/audio.wav"
                storage.upload_file(audio_key, audio_path, content_type="audio/wav")

            video.audio_storage_key = audio_key
            video.duration_ms = duration_ms or video.duration_ms
            video.status = SourceVideoStatus.extracted

        emit_stage_progress(project_id, stage, 1.0)
        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()


# ---------------------------------------------------------------------------
# Stage 2: chunk_and_diarize
# ---------------------------------------------------------------------------
# No segment may exceed this. synthesize uses each segment's own audio slice
# as the CosyVoice2 voice-clone reference, and CosyVoice2 hard-asserts that
# reference is <= 30s ("do not support extract speech token for audio longer
# than 30s"). Real diarization happily returns a 40s monologue turn, so the
# cap is applied to every chunk -- provider output and the no-speech fallback
# alike -- not just one of them. 25s leaves headroom under the 30s limit.
MAX_SEGMENT_MS = 25_000


def _cap_chunk_lengths(chunks: list[SpeakerChunk], max_ms: int) -> list[SpeakerChunk]:
    """Split any chunk longer than `max_ms` into contiguous sub-chunks,
    preserving speaker_tag and leaving shorter chunks untouched."""
    out: list[SpeakerChunk] = []
    for c in chunks:
        span = c.end_ms - c.start_ms
        if span <= max_ms:
            out.append(c)
            continue
        for start in range(c.start_ms, c.end_ms, max_ms):
            out.append(
                SpeakerChunk(
                    start_ms=start,
                    end_ms=min(start + max_ms, c.end_ms),
                    speaker_tag=c.speaker_tag,
                )
            )
    return out


@celery_app.task(bind=True, name="app.pipeline.tasks.chunk_and_diarize", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def chunk_and_diarize(self, project_id: str, source_video_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "chunk_and_diarize"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = db.get(Project, project_id) if is_uuid(project_id) else None
            video = db.get(SourceVideo, source_video_id) if is_uuid(source_video_id) else None
            if project is None or video is None or not video.audio_storage_key:
                raise ValueError("source video audio not extracted yet")
            _set_stage(db, project, stage)

            existing = db.execute(
                select(Segment).where(Segment.source_video_id == source_video_id)
            ).scalars().all()
            if existing:
                logger.info("chunk_and_diarize: %d segments already exist, skipping (idempotent)", len(existing))
                emit_stage_completed(project_id, stage)
                return project_id

            storage = get_storage()
            with tempfile.TemporaryDirectory() as tmp:
                audio_path = f"{tmp}/audio.wav"
                storage.download_file(video.audio_storage_key, audio_path)
                chunks = get_diarization_provider().chunk_and_diarize(audio_path)

            if not chunks:
                # Diarization found no speech turns. On a genuinely empty or
                # music-only file this is correct; on a short/quiet
                # single-speaker clip pyannote's VAD just misses. Either way,
                # producing zero segments silently strands the run in
                # "processing" forever (transcribe early-returns on no
                # segments). Fall back to one whole-file chunk (the length cap
                # below windows it); raise only when we can't even bound it.
                # See CONTRACTS.md #5 (no silent dead-ends).
                duration_ms = video.duration_ms or 0
                if duration_ms <= 0:
                    raise ValueError(
                        "diarization produced no speech segments and the audio "
                        "duration is unknown -- the source file may be silent, "
                        "music-only, or corrupt."
                    )
                logger.warning(
                    "chunk_and_diarize: no diarization turns; falling back to a "
                    "whole-file segment (0-%dms), windowed below.",
                    duration_ms,
                )
                chunks = [SpeakerChunk(start_ms=0, end_ms=duration_ms, speaker_tag="SPEAKER_00")]

            before = len(chunks)
            chunks = _cap_chunk_lengths(chunks, MAX_SEGMENT_MS)
            if len(chunks) != before:
                logger.info(
                    "chunk_and_diarize: split %d long turn(s) into %d segments "
                    "(cap %dms) so each stays a valid TTS voice reference.",
                    before,
                    len(chunks),
                    MAX_SEGMENT_MS,
                )

            speakers_by_tag: dict[str, Speaker] = {}
            for i, chunk in enumerate(chunks):
                speaker = speakers_by_tag.get(chunk.speaker_tag)
                if speaker is None:
                    speaker = db.execute(
                        select(Speaker).where(
                            Speaker.project_id == project_id, Speaker.diarization_tag == chunk.speaker_tag
                        )
                    ).scalar_one_or_none()
                    if speaker is None:
                        speaker = Speaker(
                            project_id=project_id,
                            label=f"Speaker {len(speakers_by_tag) + 1}",
                            diarization_tag=chunk.speaker_tag,
                        )
                        db.add(speaker)
                        db.flush()
                    speakers_by_tag[chunk.speaker_tag] = speaker

                db.add(
                    Segment(
                        project_id=project_id,
                        source_video_id=source_video_id,
                        speaker_id=speaker.id,
                        index=i,
                        start_ms=chunk.start_ms,
                        end_ms=chunk.end_ms,
                        status=SegmentStatus.pending,
                    )
                )
                emit_stage_progress(project_id, stage, (i + 1) / max(len(chunks), 1), completed=i + 1, total=len(chunks))

        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()


# ---------------------------------------------------------------------------
# Stage 3: transcribe
# ---------------------------------------------------------------------------
def _transcribe_one(audio_path: str, segment: Segment, language: str | None = None) -> None:
    bind_context(segment_id=segment.id)
    result = get_asr_provider().transcribe_chunk(
        audio_path, segment.start_ms, segment.end_ms, language=language
    )
    segment.source_text = result.text
    segment.detected_language = result.language
    segment.detected_language_confidence = result.confidence
    segment.status = SegmentStatus.transcribed


@celery_app.task(bind=True, name="app.pipeline.tasks.transcribe", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def transcribe(self, project_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "transcribe"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = _require_project(db, project_id)
            _set_stage(db, project, stage)
            segments = db.execute(
                select(Segment)
                .where(
                    Segment.project_id == project_id,
                    Segment.status.in_([SegmentStatus.pending, SegmentStatus.transcribed]),
                )
                .order_by(Segment.index)
            ).scalars().all()
            if not segments:
                # Not a benign "nothing to do": every earlier stage completed
                # yet no segment exists, so the run would otherwise strand in
                # "processing" with no error. Fail loudly instead.
                raise ValueError(
                    "transcribe: no segments to transcribe -- diarization "
                    "produced nothing for this project."
                )

            storage = get_storage()
            audio_key = _require_audio_key(db, segments[0].source_video_id)
            with tempfile.TemporaryDirectory() as tmp:
                audio_path = f"{tmp}/audio.wav"
                storage.download_file(audio_key, audio_path)
                for i, seg in enumerate(segments):
                    _transcribe_one(audio_path, seg, project.source_language)
                    emit_stage_progress(project_id, stage, (i + 1) / len(segments), completed=i + 1, total=len(segments))
        with session_scope() as db:
            project = _require_project(db, project_id)
            if project.review_language:
                # Park here. The expensive half only starts once someone has
                # confirmed the detected language via /confirm-language.
                project.status = ProjectStatus.awaiting_language_confirmation
                project.current_stage = None
                logger.info("transcribe: awaiting source-language confirmation")

        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()


# ---------------------------------------------------------------------------
# Stage 4: detect_emotion (P2 -- skipped, defaulted to neutral, if the
# project's preserve_emotion flag is off)
# ---------------------------------------------------------------------------
def _detect_emotion_one(audio_path: str, segment: Segment) -> None:
    bind_context(segment_id=segment.id)
    result = get_emotion_provider().detect(audio_path, segment.start_ms, segment.end_ms)
    segment.emotion_label = EmotionLabel(result.label)
    segment.emotion_score = result.score
    segment.status = SegmentStatus.emotion_detected


@celery_app.task(bind=True, name="app.pipeline.tasks.detect_emotion", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def detect_emotion(self, project_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "detect_emotion"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = _require_project(db, project_id)
            _set_stage(db, project, stage)
            segments = db.execute(
                select(Segment)
                .where(Segment.project_id == project_id, Segment.status == SegmentStatus.transcribed)
                .order_by(Segment.index)
            ).scalars().all()
            if not segments:
                emit_stage_completed(project_id, stage)
                return project_id

            if not project.preserve_emotion:
                for seg in segments:
                    seg.emotion_label = EmotionLabel.neutral
                    seg.emotion_score = 1.0
                    seg.status = SegmentStatus.emotion_detected
                emit_stage_progress(project_id, stage, 1.0)
                emit_stage_completed(project_id, stage)
                return project_id

            storage = get_storage()
            audio_key = _require_audio_key(db, segments[0].source_video_id)
            with tempfile.TemporaryDirectory() as tmp:
                audio_path = f"{tmp}/audio.wav"
                storage.download_file(audio_key, audio_path)
                for i, seg in enumerate(segments):
                    _detect_emotion_one(audio_path, seg)
                    emit_stage_progress(project_id, stage, (i + 1) / len(segments), completed=i + 1, total=len(segments))
        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()


# ---------------------------------------------------------------------------
# Stage 5: translate
# ---------------------------------------------------------------------------
def translate_segment(segment: Segment, target_lang: str, source_lang: str) -> None:
    """Shared by the full-project stage task and single-segment /regenerate.

    `source_lang` MUST be passed explicitly -- TranslationProvider.translate's
    src_lang default of "en" existed for call-site convenience, and every real
    call site silently relied on it instead of ever passing what ASR actually
    detected. That is the bug: a segment detected as Chinese at 98% confidence
    got translated as if it were English, with no error anywhere. See
    CONTRACTS.md #3 and #5.
    """
    bind_context(segment_id=segment.id)
    result = get_translation_provider().translate(segment.source_text or "", target_lang, src_lang=source_lang)
    segment.translated_text = result.text
    segment.status = SegmentStatus.translated


def _project_source_language(project: Project, segments: list[Segment]) -> str:
    """The confirmed source language for this project, or the ASR majority
    vote if the confirmation gate was skipped (review_language=False).

    Never falls back to a hardcoded "en": that silent substitution is exactly
    what let a 98%-confidence Chinese detection be translated as English.
    Raises if no source language is known at all, which the caller lets
    surface as a permanent (non-retried) failure. See CONTRACTS.md #3 and #5.
    """
    if project.source_language:
        return project.source_language
    from collections import Counter

    detected = [s.detected_language for s in segments if s.detected_language]
    if detected:
        return Counter(detected).most_common(1)[0][0]
    raise ValueError(
        f"project {project.id} has no confirmed source_language and no segment "
        "reported a detected_language -- cannot translate without guessing."
    )


@celery_app.task(bind=True, name="app.pipeline.tasks.translate", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def translate(self, project_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "translate"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = _require_project(db, project_id)
            _set_stage(db, project, stage)
            target_lang = _target_lang(project)
            segments = db.execute(
                select(Segment)
                .where(Segment.project_id == project_id, Segment.status == SegmentStatus.emotion_detected)
                .order_by(Segment.index)
            ).scalars().all()

            # Resolved and validated ONCE, before spending any translation
            # calls: an unsupported source language (require_source_language
            # inside translate_segment would also catch it, per-segment) fails
            # the whole stage immediately and clearly instead of burning
            # partial work first.
            source_lang = _project_source_language(project, segments)
            from app.capabilities import require_source_language

            require_source_language(source_lang)

            for i, seg in enumerate(segments):
                translate_segment(seg, target_lang, source_lang)
                emit_stage_progress(project_id, stage, (i + 1) / max(len(segments), 1), completed=i + 1, total=len(segments))
        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()


# ---------------------------------------------------------------------------
# Stage 6: synthesize
# ---------------------------------------------------------------------------
def synthesize_segment(db, storage, segment: Segment, project: Project) -> None:
    """Shared by the full-project stage task and single-segment /regenerate."""
    bind_context(segment_id=segment.id)

    with tempfile.TemporaryDirectory() as tmp:
        voice_ref_path = None
        voice_ref_text = None
        if project.clone_voice and segment.speaker_id:
            speaker = db.get(Speaker, segment.speaker_id)
            if speaker and speaker.reference_clip_url:
                # reference_clip_url is a storage key (set during voice-cloning
                # setup, P3) -- TTS providers need a local file, so pull it down
                # once per render rather than assuming the provider can fetch it.
                voice_ref_path = f"{tmp}/reference_clip.wav"
                storage.download_file(speaker.reference_clip_url, voice_ref_path)
                voice_ref_text = segment.source_text

        if voice_ref_path is None and segment.source_text:
            # P3's per-speaker reference clip is never populated by any stage
            # today, and zero-shot TTS providers (CosyVoice2) have no
            # synthesis path at all without *some* reference audio -- the
            # segment's own source-language audio is a perfectly good stand-in
            # (it's literally that speaker's voice) and needs nothing beyond
            # what extract_audio/chunk_and_diarize already produced.
            video = db.get(SourceVideo, segment.source_video_id)
            if video and video.audio_storage_key:
                # Best-effort: a provider that doesn't need a reference (the
                # mock) must still render if the extracted audio is missing or
                # ffmpeg is unavailable, so failures here degrade to "no
                # reference" rather than failing the whole segment. Providers
                # that *do* require one raise their own clear error.
                try:
                    full_audio_path = f"{tmp}/full_audio.wav"
                    storage.download_file(video.audio_storage_key, full_audio_path)
                    with ffmpeg_utils.extract_audio_slice(
                        full_audio_path, segment.start_ms, segment.end_ms
                    ) as slice_path:
                        voice_ref_path = f"{tmp}/reference_clip.wav"
                        shutil.copyfile(slice_path, voice_ref_path)
                    voice_ref_text = segment.source_text
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "could not derive a voice reference from source audio (%s): %s",
                        video.audio_storage_key,
                        exc,
                    )
                    voice_ref_path = None
                    voice_ref_text = None

        emotion = None
        if project.preserve_emotion and segment.emotion_label:
            emotion = EmotionResult(label=segment.emotion_label.value, score=segment.emotion_score or 0.0)

        request = SynthesisRequest(
            text=segment.translated_text or "",
            target_lang=_target_lang(project),
            voice_reference_path=voice_ref_path,
            voice_reference_text=voice_ref_text,
            emotion=emotion,
            extra={"tts_model": project.tts_model} if project.tts_model else {},
        )
        result = get_tts_provider().synthesize(request)

        key = f"projects/{project.id}/segments/{segment.id}/tts.wav"
        storage.upload_file(key, result.local_audio_path, content_type="audio/wav")

    segment.tts_audio_url = key
    segment.tts_duration_ms = result.duration_ms
    original_ms = max(segment.end_ms - segment.start_ms, 1)
    segment.sync_offset_pct = round(100.0 * (result.duration_ms - original_ms) / original_ms, 2)
    segment.status = SegmentStatus.synthesized


@celery_app.task(bind=True, name="app.pipeline.tasks.synthesize", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def synthesize(self, project_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "synthesize"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = _require_project(db, project_id)
            _set_stage(db, project, stage)
            storage = get_storage()
            segments = db.execute(
                select(Segment)
                .where(Segment.project_id == project_id, Segment.status == SegmentStatus.translated)
                .order_by(Segment.index)
            ).scalars().all()
            for i, seg in enumerate(segments):
                synthesize_segment(db, storage, seg, project)
                db.flush()
                emit_segment_ready(project_id, seg.id)
                emit_stage_progress(project_id, stage, (i + 1) / max(len(segments), 1), completed=i + 1, total=len(segments))
        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()


# ---------------------------------------------------------------------------
# Stage 7: mux_export
# ---------------------------------------------------------------------------
@celery_app.task(bind=True, name="app.pipeline.tasks.mux_export", autoretry_for=_RETRYABLE, dont_autoretry_for=_PERMANENT, max_retries=3,
                  retry_backoff=True)
def mux_export(self, project_id: str) -> str:
    bind_context(project_id=project_id)
    stage = "mux_export"
    emit_stage_started(project_id, stage)
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")
            _set_stage(db, project, stage)
            segments = db.execute(
                select(Segment)
                .where(Segment.project_id == project_id)
                .order_by(Segment.index)
            ).scalars().all()
            if not segments or any(s.status != SegmentStatus.synthesized for s in segments):
                raise ValueError("not all segments are synthesized yet")

            source_video = db.get(SourceVideo, segments[0].source_video_id)
            if source_video is None:
                raise ValueError("source video not found for these segments")
            storage = get_storage()

            export = db.execute(
                select(ExportJob).where(
                    ExportJob.project_id == project_id, ExportJob.status != ExportStatus.ready
                )
            ).scalars().first()
            if export is None:
                export = ExportJob(project_id=project_id, status=ExportStatus.running)
                db.add(export)
                db.flush()
            export.status = ExportStatus.running

            with tempfile.TemporaryDirectory() as tmp:
                video_path = f"{tmp}/source.mp4"
                storage.download_file(source_video.storage_key, video_path)

                # (local path, start_ms) -- each clip is laid at its own
                # timecode so the dub stays aligned with the picture.
                placements: list[tuple[str, int]] = []
                for i, seg in enumerate(segments):
                    if not seg.tts_audio_url:
                        raise ValueError(f"segment {seg.id} has no rendered audio to mux")
                    p = f"{tmp}/seg_{i:04d}.wav"
                    storage.download_file(seg.tts_audio_url, p)
                    placements.append((p, seg.start_ms))
                    emit_stage_progress(project_id, stage, 0.1 + 0.6 * (i + 1) / len(segments))

                out_path = f"{tmp}/output.mp4"
                ffmpeg_utils.mux_timeline(video_path, placements, out_path)

                out_key = f"projects/{project_id}/exports/{export.id}/output.mp4"
                storage.upload_file(out_key, out_path, content_type="video/mp4")

            qa_report = {
                "segments": [
                    {
                        "segment_id": s.id,
                        "sync_offset_pct": s.sync_offset_pct,
                        "emotion_label": s.emotion_label.value if s.emotion_label else None,
                    }
                    for s in segments
                ],
                "overall": {
                    "segment_count": len(segments),
                    "avg_sync_offset_pct": round(
                        sum(abs(s.sync_offset_pct or 0) for s in segments) / len(segments), 2
                    ),
                },
            }

            export.output_url = out_key
            export.qa_report = qa_report
            export.status = ExportStatus.ready
            from datetime import datetime, timezone

            export.completed_at = datetime.now(timezone.utc)

            for s in segments:
                s.status = SegmentStatus.muxed
            project.status = ProjectStatus.ready
            project.current_stage = None
            # Clear any failure recorded by an earlier attempt -- otherwise a
            # project that later succeeds still reports the stale error to the
            # dashboard alongside status="ready".
            project.error_message = None
            project.error_is_permanent = None

        emit_stage_progress(project_id, stage, 1.0)
        emit_stage_completed(project_id, stage)
        return project_id
    except Exception as exc:  # noqa: BLE001
        _mark_project_failed(project_id, stage, exc)
        raise
    finally:
        clear_context()
