from __future__ import annotations

import logging

from app.providers.base import DiarizationProvider, SpeakerChunk

# Imported as a module, not `from ... import probe_duration_ms`: binding the
# function object here would freeze whatever was current at import time, so a
# later patch of ffmpeg_utils.probe_duration_ms would or wouldn't be visible
# depending purely on module import order.
from app.pipeline import ffmpeg_utils

logger = logging.getLogger(__name__)

CHUNK_MS = 4000  # fixed-width fallback chunking; real VAD would find silence boundaries


class MockDiarizationProvider(DiarizationProvider):
    """Deterministic stand-in for Silero VAD + pyannote-audio.

    Splits the audio into fixed-width windows and alternates two speaker
    tags, which is enough for the API/frontend contract (multiple segments,
    at least one speaker change) without needing any model weights.
    """

    def chunk_and_diarize(self, audio_path: str) -> list[SpeakerChunk]:
        total_ms = ffmpeg_utils.probe_duration_ms(audio_path)
        chunks: list[SpeakerChunk] = []
        speaker_idx = 0
        t = 0
        i = 0
        while t < total_ms:
            end = min(t + CHUNK_MS, total_ms)
            # New "speaker" every 3rd chunk so multi-speaker projects have
            # something to diarize in the editor.
            if i and i % 3 == 0:
                speaker_idx = (speaker_idx + 1) % 2
            chunks.append(SpeakerChunk(start_ms=t, end_ms=end, speaker_tag=f"SPEAKER_{speaker_idx:02d}"))
            t = end
            i += 1
        if not chunks:
            chunks = [SpeakerChunk(start_ms=0, end_ms=max(total_ms, 1000), speaker_tag="SPEAKER_00")]
        logger.info("mock diarization produced %d chunks", len(chunks))
        return chunks
