"""Builds and kicks off the Celery chains -- called from
POST /api/projects/{id}/process and .../confirm-language.

Each link's return value (always the project_id) becomes the first positional
arg of the next, per Celery chain semantics; stage-specific extra args are
bound with .s(...).

The pipeline is deliberately split in two. Everything up to and including ASR
is cheap; everything after it is not (TTS runs minutes per sentence on CPU).
So when `review_language` is on, the run stops after transcribe and waits for
a human to confirm or correct the detected source language. A wrong
auto-detect that runs straight through produces a dub in the wrong language
and wastes the entire expensive half. See CONTRACTS.md #5.
"""
from __future__ import annotations

from celery import chain

from app.pipeline.tasks import (
    chunk_and_diarize,
    detect_emotion,
    extract_audio,
    mux_export,
    synthesize,
    transcribe,
    translate,
)


def start_pipeline(project_id: str, source_video_id: str, *, review_language: bool = True):
    """Extract -> diarize -> transcribe, then either stop for confirmation or
    continue straight through."""
    links = [
        extract_audio.s(project_id, source_video_id),
        chunk_and_diarize.s(source_video_id),
        transcribe.s(),
    ]
    if not review_language:
        links += _expensive_stages()
    return chain(*links).apply_async()


def continue_pipeline(project_id: str):
    """Resume after the language has been confirmed."""
    return chain(*_expensive_stages()).apply_async(args=[project_id])


def _expensive_stages():
    return [
        detect_emotion.s(),
        translate.s(),
        synthesize.s(),
        mux_export.s(),
    ]
