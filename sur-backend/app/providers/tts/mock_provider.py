from __future__ import annotations

import math
import struct
import tempfile
import wave

from app.providers.base import SynthesisRequest, SynthesisResult, TTSProvider

SAMPLE_RATE = 24000
_MS_PER_CHAR = 60  # crude but deterministic "reading speed" for a fake duration


class MockTTSProvider(TTSProvider):
    """Deterministic stand-in for CosyVoice2/Indic Parler-TTS.

    Generates a real, playable WAV (a short sine tone) whose duration is a
    stable function of the input text length, so the frontend's waveform
    player, duration displays, and sync-offset math all have something real
    to work against -- without pulling in a TTS model.
    """

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        duration_ms = request.target_duration_ms or max(500, len(request.text) * _MS_PER_CHAR)
        n_samples = int(SAMPLE_RATE * duration_ms / 1000)
        freq = 220.0
        # Vary pitch slightly by emotion so a human skimming a batch of mock
        # renders can tell them apart.
        if request.emotion is not None:
            freq += {"anger": 120, "happiness": 60, "fear": 40, "surprise": 80}.get(
                request.emotion.label, 0
            )

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            frames = bytearray()
            for i in range(n_samples):
                val = int(3000 * math.sin(2 * math.pi * freq * (i / SAMPLE_RATE)))
                frames += struct.pack("<h", val)
            wf.writeframes(bytes(frames))

        return SynthesisResult(local_audio_path=tmp.name, duration_ms=duration_ms, sample_rate=SAMPLE_RATE)
