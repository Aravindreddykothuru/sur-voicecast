from __future__ import annotations

from app.providers.base import EmotionProvider, EmotionResult

_CYCLE = ["neutral", "happiness", "anger", "sadness", "surprise", "fear"]


class MockEmotionProvider(EmotionProvider):
    """Deterministic stand-in for the wav2vec2 SER classifier.

    Cycles through all six labels keyed on chunk start time, so the segment
    editor's emotion badges (and their color-coding) can be exercised
    end-to-end without a model.
    """

    def available_labels(self) -> list[str]:
        # The cycle is this provider's entire "model", so it is the honest
        # answer to "what can you emit?" -- still derived, not a second list.
        return list(_CYCLE)

    def detect(self, audio_path: str, start_ms: int, end_ms: int) -> EmotionResult:
        label = _CYCLE[(start_ms // 4000) % len(_CYCLE)]
        return EmotionResult(label=label, score=0.8, valence=0.0, arousal=0.5)
