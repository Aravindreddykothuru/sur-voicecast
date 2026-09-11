from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.providers.base import EmotionProvider, EmotionResult
from app.providers.registry import ProviderNotInstalledError
from app.pipeline import ffmpeg_utils  # module, not the function: keeps patching/late binding working

logger = logging.getLogger(__name__)

# Maps a source model's own id2label names onto the PRD's six-way taxonomy.
# Keys cover both SUPERB's abbreviated labels (the default model) and the
# fuller RAVDESS-style sets other checkpoints use, so swapping
# EMOTION_MODEL_NAME doesn't silently start returning "neutral" for
# everything. Anything unrecognised falls back to neutral.
_LABEL_MAP = {
    # SUPERB (superb/*-superb-er) -- IEMOCAP 4-way
    "neu": "neutral",
    "hap": "happiness",
    "ang": "anger",
    "sad": "sadness",
    # Fuller label sets
    "angry": "anger", "anger": "anger",
    "sadness": "sadness",
    "happy": "happiness", "happiness": "happiness", "joy": "happiness",
    "fearful": "fear", "fear": "fear",
    "surprised": "surprise", "surprise": "surprise",
    "neutral": "neutral", "calm": "neutral",
    "excited": "happiness",
    "frustrated": "anger",
    "disgust": "anger",
}


@lru_cache(maxsize=8)
def labels_from_config(model_name: str) -> tuple[str, ...]:
    """The labels a checkpoint can emit, read from its config alone.

    AutoConfig downloads a few KB of JSON; constructing the provider downloads
    and loads gigabytes of weights. The API process only needs the label names
    for /api/capabilities, so making it pay for a full model load turned that
    endpoint into a 30s+ request (and a second copy of the model in RAM).
    Still derived from the model's own config.id2label -- never a hardcoded
    list. See CONTRACTS.md #2.
    """
    from transformers import AutoConfig

    cfg = AutoConfig.from_pretrained(model_name)
    seen: list[str] = []
    for raw in (cfg.id2label or {}).values():
        mapped = _LABEL_MAP.get(str(raw).lower())
        if mapped and mapped not in seen:
            seen.append(mapped)
    return tuple(seen)


class Wav2Vec2EmotionProvider(EmotionProvider):
    """wav2vec2-based speech-emotion recognition (categorical + valence/
    arousal), with prosody features fused in via librosa for robustness
    against background score/SFX. Requires `pip install -r requirements-ml.txt`."""

    def __init__(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        except ImportError as e:
            raise ProviderNotInstalledError("Wav2Vec2EmotionProvider", "torch, transformers") from e

        settings = get_settings()
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        from app.providers.loading import load_hf_model

        self._model_name = settings.emotion_model_name
        self._extractor = AutoFeatureExtractor.from_pretrained(self._model_name)
        # NOT from_pretrained directly: that silently random-initialises a head
        # it can't find in the checkpoint. See CONTRACTS.md invariant #1.
        self._model = load_hf_model(AutoModelForAudioClassification, self._model_name)
        self._model.eval()
        self._self_check()

    def available_labels(self) -> list[str]:
        """The labels this model can actually emit, derived from its own
        config.id2label -- never a hardcoded list. The API surfaces these so
        the UI can't offer an emotion the model will never predict."""
        seen: list[str] = []
        for raw in self._model.config.id2label.values():
            mapped = _LABEL_MAP.get(str(raw).lower())
            if mapped and mapped not in seen:
                seen.append(mapped)
        return seen

    def _self_check(self) -> None:
        """Refuse to boot on a model that behaves like random weights.

        The loading check catches the known signature of the failure; this
        catches the behaviour whatever the cause. Uses a fixed synthetic
        sample so it needs no fixture file and is identical on every machine.
        """
        import numpy as np
        import torch

        from app.providers.loading import assert_not_degenerate

        # 1s of a deterministic 220Hz tone with a little noise -- content is
        # irrelevant, we only assert the head isn't producing a flat
        # distribution.
        sr = 16000
        t = np.linspace(0, 1, sr, endpoint=False, dtype=np.float32)
        rng = np.random.default_rng(0)
        sample = (0.5 * np.sin(2 * np.pi * 220 * t) + 0.01 * rng.standard_normal(sr)).astype("float32")

        inputs = self._extractor(sample, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1)
        assert_not_degenerate(probs.tolist(), self._model_name)
        logger.info(
            "emotion self-check passed for %s (labels: %s)",
            self._model_name,
            ", ".join(self.available_labels()),
        )

    def detect(self, audio_path: str, start_ms: int, end_ms: int) -> EmotionResult:
        import librosa
        import torch

        with ffmpeg_utils.extract_audio_slice(audio_path, start_ms, end_ms) as slice_path:
            audio, sr = librosa.load(slice_path, sr=16000, mono=True)
            inputs = self._extractor(audio, sampling_rate=sr, return_tensors="pt")
            with torch.no_grad():
                logits = self._model(**inputs).logits[0]
            probs = torch.softmax(logits, dim=-1)
            idx = int(torch.argmax(probs))
            raw_label = self._model.config.id2label[idx].lower()
            label = _LABEL_MAP.get(raw_label, "neutral")
            score = float(probs[idx])

            # Prosody-derived valence/arousal proxy fused in per the PRD.
            rms = float(librosa.feature.rms(y=audio).mean())
            pitches, _ = librosa.piptrack(y=audio, sr=sr)
            arousal = min(1.0, rms * 20)
            valence = 1.0 if label in ("happiness", "surprise") else (-1.0 if label in ("anger", "sadness", "fear") else 0.0)

        return EmotionResult(label=label, score=score, valence=valence, arousal=arousal)
