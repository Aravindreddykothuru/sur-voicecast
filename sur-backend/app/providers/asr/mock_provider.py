from __future__ import annotations

from app.providers.base import ASRProvider, TranscriptResult


class MockASRProvider(ASRProvider):
    """Deterministic stand-in for faster-whisper+WhisperX.

    Returns placeholder but *stable* text keyed on the chunk's timing, so a
    frontend developer sees distinct, orderable segments rather than
    identical text everywhere -- and so tests can assert on exact output.
    """

    def transcribe_chunk(self, audio_path: str, start_ms: int, end_ms: int, language: str | None = None) -> TranscriptResult:
        seconds = start_ms // 1000
        return TranscriptResult(
            text=f"[mock transcript at {seconds}s] This is placeholder dialogue.",
            confidence=0.95,
            language=language or "en",
        )
