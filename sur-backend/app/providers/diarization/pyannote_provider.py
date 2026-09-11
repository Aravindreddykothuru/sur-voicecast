from __future__ import annotations

import logging

from app.config import get_settings, require_hf_token
from app.providers.base import DiarizationProvider, SpeakerChunk
from app.providers.registry import ProviderNotInstalledError

logger = logging.getLogger(__name__)


class PyannoteDiarizationProvider(DiarizationProvider):
    """Silero VAD for utterance boundaries + pyannote-audio for per-speaker
    IDs. Requires `pip install -r requirements-ml.txt` and, for pyannote, a
    HuggingFace token with access to the pretrained pipeline accepted."""

    def __init__(self) -> None:
        try:
            import torch  # noqa: F401
            from pyannote.audio import Pipeline  # noqa: F401
        except ImportError as e:
            raise ProviderNotInstalledError("PyannoteDiarizationProvider", "torch, pyannote.audio") from e

        # pyannote.audio 3.3.1's own pipeline code (pipelines/speaker_diarization.py
        # et al.) still references the deprecated `np.NAN` alias, which NumPy 2.0
        # removed outright -- but pyannote-core/pyannote-metrics *require*
        # numpy>=2.0, so downgrading numpy isn't an option (it'd break scipy's
        # ABI instead). `np.nan` is unchanged; just restore the old name.
        import numpy as np

        if not hasattr(np, "NAN"):
            np.NAN = np.nan  # type: ignore[attr-defined]

        settings = get_settings()
        import torch
        from pyannote.audio import Pipeline

        self._device = torch.device(settings.asr_device if torch.cuda.is_available() else "cpu")
        self._vad_model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
        self._diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=require_hf_token("DIARIZATION_PROVIDER=real (pyannote)")
        )
        self._diarization_pipeline.to(self._device)

    def chunk_and_diarize(self, audio_path: str) -> list[SpeakerChunk]:
        diarization = self._diarization_pipeline(audio_path)
        chunks: list[SpeakerChunk] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            chunks.append(
                SpeakerChunk(
                    start_ms=int(turn.start * 1000),
                    end_ms=int(turn.end * 1000),
                    speaker_tag=str(speaker),
                )
            )
        chunks.sort(key=lambda c: c.start_ms)
        return chunks
