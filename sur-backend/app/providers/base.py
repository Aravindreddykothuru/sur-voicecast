"""Abstract provider interfaces -- one per pipeline stage.

This is the core design requirement from the backend build prompt: pipeline
tasks (app/pipeline/tasks.py) NEVER import a model library directly. They
only ever call through one of these four interfaces, obtained from
app.providers.registry. Swapping faster-whisper for a Triton endpoint, or
CosyVoice2 for Chatterbox, means writing a new subclass here and flipping an
env var -- not touching a single Celery task.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SpeakerChunk:
    """One utterance-level chunk produced by chunk_and_diarize."""

    start_ms: int
    end_ms: int
    speaker_tag: str  # provider-local id, e.g. "SPEAKER_00"; mapped to a Speaker row by the task


@dataclass
class TranscriptResult:
    text: str
    confidence: float = 1.0
    language: str = "en"


@dataclass
class EmotionResult:
    label: str  # one of: anger, sadness, happiness, fear, surprise, neutral
    score: float  # confidence in `label`, 0..1
    valence: float = 0.0  # -1..1
    arousal: float = 0.0  # 0..1


@dataclass
class TranslationResult:
    text: str
    src_lang: str
    target_lang: str


@dataclass
class SynthesisRequest:
    text: str
    target_lang: str
    voice_reference_path: str | None = None  # local wav for zero-shot cloning (P3)
    voice_reference_text: str | None = None  # transcript matching voice_reference_path, if any
    emotion: EmotionResult | None = None  # conditions prosody (P2)
    target_duration_ms: int | None = None  # sync-fit hint (P4); providers may ignore it
    extra: dict = field(default_factory=dict)


@dataclass
class SynthesisResult:
    local_audio_path: str
    duration_ms: int
    sample_rate: int = 24000


class DiarizationProvider(ABC):
    @abstractmethod
    def chunk_and_diarize(self, audio_path: str) -> list[SpeakerChunk]:
        """VAD-segment `audio_path` and assign a speaker tag to each chunk."""


class ASRProvider(ABC):
    @abstractmethod
    def transcribe_chunk(
        self, audio_path: str, start_ms: int, end_ms: int, language: str | None = None
    ) -> TranscriptResult:
        """Transcribe the [start_ms, end_ms) slice of `audio_path`.

        `language` overrides detection for this call (a reviewer correcting a
        wrong auto-detect). None means detect. The result reports the language
        actually used, never an assumed one."""


class EmotionProvider(ABC):
    @abstractmethod
    def detect(self, audio_path: str, start_ms: int, end_ms: int) -> EmotionResult:
        """Classify the emotional register of one audio chunk."""

    @abstractmethod
    def available_labels(self) -> list[str]:
        """The labels this provider can actually emit.

        Must be derived from the loaded model rather than hardcoded: the API
        publishes this so the UI never offers an emotion the model will never
        predict. See CONTRACTS.md invariant #2."""


class TranslationProvider(ABC):
    @abstractmethod
    def translate(self, text: str, target_lang: str, src_lang: str = "en") -> TranslationResult:
        """Translate `text` from `src_lang` into `target_lang`, meaning-preserving."""


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Render `request.text` as speech, honoring voice/emotion conditioning
        when provided."""
