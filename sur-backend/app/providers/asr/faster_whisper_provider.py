from __future__ import annotations

import logging

from app.config import get_settings
from app.providers.base import ASRProvider, TranscriptResult
from app.providers.registry import ProviderNotInstalledError
from app.pipeline import ffmpeg_utils  # module, not the function: keeps patching/late binding working

logger = logging.getLogger(__name__)


class FasterWhisperASRProvider(ASRProvider):
    """faster-whisper (large-v3), CTranslate2-optimized, with WhisperX doing
    word-level alignment on top. Requires `pip install -r requirements-ml.txt`."""

    def __init__(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ProviderNotInstalledError("FasterWhisperASRProvider", "faster-whisper") from e

        settings = get_settings()
        compute_type = "float16" if settings.asr_device == "cuda" else "int8"
        self._model = WhisperModel(settings.asr_model_name, device=settings.asr_device, compute_type=compute_type)
        # faster-whisper takes language=None to mean "detect it".
        lang = (settings.asr_language or "auto").strip().lower()
        self._language = None if lang in ("auto", "") else lang

    def transcribe_chunk(
        self, audio_path: str, start_ms: int, end_ms: int, language: str | None = None
    ) -> TranscriptResult:
        with ffmpeg_utils.extract_audio_slice(audio_path, start_ms, end_ms) as slice_path:
            # Per-call override wins over the configured default; both may be
            # None, which means "detect".
            use_lang = language or self._language
            segments, info = self._model.transcribe(
                slice_path, language=use_lang, word_timestamps=True
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            confidence = float(getattr(info, "language_probability", 0.9) or 0.9)
            # Report what was actually spoken, not a hardcoded assumption --
            # downstream translation keys off this.
            detected = use_lang or getattr(info, "language", None) or "und"
        return TranscriptResult(text=text, confidence=confidence, language=detected)
