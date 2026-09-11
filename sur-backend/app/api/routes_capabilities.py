"""GET /api/capabilities -- what this deployment can actually do.

The frontend renders its target-language picker and emotion controls purely
from this response. It holds no lists of its own, so it can never offer an
option the backend would then fail on (which is exactly how 5 unsupported
languages reached the UI). See CONTRACTS.md invariant #2.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.capabilities import EMOTION_COLOR_FALLBACK, EMOTION_COLORS, SOURCE_LANGUAGES, SUPPORTED_LANGUAGES
from app.config import get_settings
from app.providers.registry import get_emotion_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["capabilities"])


class LanguageOut(BaseModel):
    code: str
    display_name: str
    flores_code: str
    tts_available: bool


class EmotionOut(BaseModel):
    label: str
    # Position in the list this response returns, not a hardcoded ordinal --
    # the frontend maps index -> CSS custom property (--emo-1..4) rather than
    # keying a color table off the label string, so a model swap that adds or
    # renames labels can't silently point at the wrong color. See
    # CONTRACTS.md #2.
    index: int
    color: str


class SourceLanguageOut(BaseModel):
    code: str
    display_name: str


class CapabilitiesOut(BaseModel):
    languages: list[LanguageOut]
    # What this engine can transcribe+correctly-translate FROM. Distinct from
    # `languages` (dub-INTO targets) -- conflating them is how a wrong
    # auto-detect (e.g. Chinese) used to get silently translated as if it
    # were English. See CONTRACTS.md #2 and #3.
    source_languages: list[SourceLanguageOut]
    emotions: list[EmotionOut]
    providers: dict[str, str]
    # Below this the UI must render "uncertain" rather than the label itself.
    # Served so the floor is one number in one place, not a frontend constant.
    emotion_confidence_floor: float
    # Whether ASR_LANGUAGE=auto -- gates the "Autodetect" option in the New
    # Dubbing modal's source-language step. False means this deployment
    # pins a fixed ASR language, so autodetect isn't actually available.
    asr_autodetect: bool
    # Conservative single summary of where real providers actually run (see
    # Settings.compute_device) -- drives the Runtime panel and the "~2 min
    # per sentence on CPU" warning copy. Never "cuda" unless every
    # GPU-relevant stage is actually configured for it.
    device: str
    max_upload_mb: int
    accepted_formats: list[str]


@router.get("/capabilities", response_model=CapabilitiesOut)
def get_capabilities() -> CapabilitiesOut:
    settings = get_settings()

    # Derived from the loaded model's own config.id2label, never hardcoded.
    # If the emotion model can't be loaded we return an empty list rather than
    # a plausible-looking default: the UI then shows nothing to pick, which is
    # the honest signal that emotion support is down. See CONTRACTS.md #3.
    emotion_labels = _emotion_labels(settings)

    return CapabilitiesOut(
        languages=[
            LanguageOut(
                code=lang.code,
                display_name=lang.name,
                flores_code=lang.flores,
                tts_available=lang.tts_supported,
            )
            for lang in SUPPORTED_LANGUAGES
        ],
        source_languages=[
            SourceLanguageOut(code=lang.code, display_name=lang.name)
            for lang in SOURCE_LANGUAGES
        ],
        emotions=[
            EmotionOut(label=label, index=i, color=EMOTION_COLORS.get(label, EMOTION_COLOR_FALLBACK))
            for i, label in enumerate(emotion_labels)
        ],
        emotion_confidence_floor=settings.emotion_confidence_floor,
        providers={
            "asr": settings.asr_provider,
            "diarization": settings.diarization_provider,
            "translation": settings.translation_provider,
            "emotion": settings.emotion_provider,
            "tts": settings.tts_provider,
        },
        asr_autodetect=settings.asr_autodetect,
        device=settings.compute_device,
        max_upload_mb=settings.max_upload_mb,
        accepted_formats=settings.accepted_video_format_list,
    )


def _emotion_labels(settings) -> list[str]:
    """Labels the configured emotion model can emit.

    For a real model this reads config.id2label only (a few KB) rather than
    constructing the provider -- the API holds no models, and loading one here
    made this endpoint take 30s+ and duplicate gigabytes in RAM. The workers
    still do the full fail-loud load and self-check at startup.

    On failure this returns [] rather than a plausible default: an empty
    emotion picker is the honest signal that emotion support is down.
    """
    try:
        if settings.emotion_provider == "real":
            from app.providers.emotion.wav2vec2_provider import labels_from_config

            return list(labels_from_config(settings.emotion_model_name))
        return get_emotion_provider().available_labels()
    except Exception:  # noqa: BLE001
        logger.exception("emotion labels unavailable; reporting none")
        return []
