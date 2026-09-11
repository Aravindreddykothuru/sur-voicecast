from __future__ import annotations

import logging
import os
import tempfile

from app.config import get_settings
from app.providers.base import SynthesisRequest, SynthesisResult, TTSProvider
from app.providers.registry import ProviderNotInstalledError

logger = logging.getLogger(__name__)

# CosyVoice2's own EmotionLabel-shaped adjectives for its natural-language
# instruct string (see inference_instruct2's `<|endofprompt|>` convention).
_EMOTION_ADJECTIVES = {
    "anger": "angry", "sadness": "sad", "happiness": "happy",
    "fear": "fearful", "surprise": "surprised", "neutral": "neutral",
}

# sur-backend/ -- app/providers/tts/this_file.py is four levels down.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _resolve_model_dir(name: str) -> str:
    """Let TTS_MODEL_NAME be a repo-relative path (e.g.
    `.tools/models/CosyVoice2-0.5B`) so the same .env works on another machine
    or inside the container, where an absolute host path wouldn't exist.
    A bare repo id (no such directory) is passed through untouched for
    CosyVoice2 to resolve via ModelScope.
    """
    if os.path.isabs(name):
        return name
    candidate = os.path.join(_BACKEND_ROOT, name)
    return candidate if os.path.isdir(candidate) else name


class CosyVoiceTTSProvider(TTSProvider):
    """CosyVoice 2: zero-shot voice cloning + multilingual + emotional
    prosody in one model, matching the PRD's choice for P2/P3 together.

    NOTE: CosyVoice2 is distributed as a source checkout, not a pip package
    (see requirements-ml.txt comment) -- this loads it via its documented
    Python API once installed. Confirm its license permits your intended
    commercial use before shipping cloned voices (see PRD risk: "Model
    licensing").
    """

    def __init__(self) -> None:
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
        except ImportError as e:
            raise ProviderNotInstalledError(
                "CosyVoiceTTSProvider", "cosyvoice (see requirements-ml.txt comment)"
            ) from e

        settings = get_settings()
        from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore

        self._engine = CosyVoice2(_resolve_model_dir(settings.tts_model_name))

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        import soundfile as sf
        import torch

        if not request.voice_reference_path:
            # CosyVoice2 dropped CosyVoice1's spk_id-based inference_instruct
            # (calling it on a CosyVoice2 instance raises an assertion) -- both
            # of its real synthesis paths (zero_shot, instruct2) need *some*
            # reference clip. app.pipeline.tasks.synthesize_segment always
            # supplies one (falling back to the segment's own source audio),
            # so reaching here means that contract was broken upstream.
            raise RuntimeError(
                "CosyVoice2 requires a voice_reference_path (no text-only synthesis mode exists); "
                "the caller must supply one, e.g. the segment's own source-language audio slice."
            )

        emotion_label = request.emotion.label if request.emotion else "neutral"
        adjective = _EMOTION_ADJECTIVES.get(emotion_label, "neutral")
        instruct_text = f"Speak in a {adjective} tone.<|endofprompt|>"

        chunks = list(
            self._engine.inference_instruct2(request.text, instruct_text, request.voice_reference_path)
        )
        if not chunks:
            raise RuntimeError("CosyVoice2 produced no audio for this segment")
        speech = torch.cat([c["tts_speech"] for c in chunks], dim=1)

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)  # release our handle first -- see ffmpeg_utils.extract_audio_slice
        sf.write(path, speech.numpy().T, self._engine.sample_rate)
        duration_ms = int(1000 * speech.shape[-1] / self._engine.sample_rate)
        return SynthesisResult(local_audio_path=path, duration_ms=duration_ms, sample_rate=self._engine.sample_rate)
