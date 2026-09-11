"""The single source of truth for what this backend can actually do.

Why this exists: the frontend used to carry its own hand-written list of 12
target languages. The translation provider only had FLORES codes for 7 of
them, so picking Gujarati, Punjabi, Odia, Assamese or Urdu raised ValueError
deep in the translate stage and killed the whole job. Two lists, one of them
wrong, no test connecting them.

Nothing may hardcode a language list again. The frontend renders whatever
GET /api/capabilities returns; the translation provider derives its FLORES
mapping from here; a test asserts every entry is complete.

See CONTRACTS.md, invariant #2.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str          # what the API and DB speak, e.g. "te"
    name: str          # what the UI shows, e.g. "Telugu"
    flores: str        # what IndicTrans2 needs, e.g. "tel_Telu"
    tts_supported: bool = True


# Every entry MUST carry a FLORES code: an entry without one is a language the
# UI would offer and the pipeline would then fail on. tests/test_capabilities.py
# enforces that, so adding a row without a mapping fails the build.
SUPPORTED_LANGUAGES: tuple[Language, ...] = (
    Language("hi", "Hindi", "hin_Deva"),
    Language("te", "Telugu", "tel_Telu"),
    Language("ta", "Tamil", "tam_Taml"),
    Language("kn", "Kannada", "kan_Knda"),
    Language("ml", "Malayalam", "mal_Mlym"),
    Language("bn", "Bengali", "ben_Beng"),
    Language("mr", "Marathi", "mar_Deva"),
    Language("gu", "Gujarati", "guj_Gujr"),
    Language("pa", "Punjabi", "pan_Guru"),
    Language("or", "Odia", "ory_Orya"),
    Language("as", "Assamese", "asm_Beng"),
    Language("ur", "Urdu", "urd_Arab"),
)

LANGUAGES_BY_CODE: dict[str, Language] = {lang.code: lang for lang in SUPPORTED_LANGUAGES}

# Derived, never hand-maintained: the translation provider reads this.
FLORES_CODES: dict[str, str] = {lang.code: lang.flores for lang in SUPPORTED_LANGUAGES}


def require_language(code: str) -> Language:
    """Resolve a target (dub-into) language or fail with the full supported set.

    Deliberately raises instead of falling back to a default: silently dubbing
    into the wrong language is worse than refusing. See CONTRACTS.md #3.
    """
    return _require(code, LANGUAGES_BY_CODE, "target")


# Source (transcribe-from) languages this engine can correctly translate.
# English uses IndicTrans2's en-indic direction; every Indic language below
# round-trips through indic-en / indic-indic. This is NOT the same set as
# SUPPORTED_LANGUAGES conceptually (that one is "what can we dub into"), it
# just happens to be English + the identical Indic list, because that's what
# ai4bharat/indictrans2-{indic-en,indic-indic} actually cover.
#
# A source language NOT in this set (the original bug: ASR detected "zh" at
# 98% confidence, and translation silently ran it through the en-indic model
# anyway, producing confident nonsense) must be refused, not guessed. See
# CONTRACTS.md #3 and #5.
SOURCE_LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", "eng_Latn"),
) + SUPPORTED_LANGUAGES

SOURCE_LANGUAGES_BY_CODE: dict[str, Language] = {lang.code: lang for lang in SOURCE_LANGUAGES}


def require_source_language(code: str) -> Language:
    """Resolve a source (transcribed-from) language or fail with the full
    supported set. See CONTRACTS.md #3 -- this is the guard the original bug
    had none of: ASR can detect (and did detect) languages this pipeline has
    no correct translation path for, and that must stop the run rather than
    silently mistranslate.
    """
    return _require(code, SOURCE_LANGUAGES_BY_CODE, "source")


def _require(code: str, table: dict[str, Language], kind: str) -> Language:
    lang = table.get(code)
    if lang is None:
        raise ValueError(
            f"Unsupported {kind} language {code!r}. Supported {kind} languages: "
            f"{', '.join(sorted(table))}. "
            f"Add it to app/capabilities.{'SOURCE_LANGUAGES' if kind == 'source' else 'SUPPORTED_LANGUAGES'} "
            "(with its FLORES code and a real translation path) rather than special-casing it here."
        )
    if not lang.flores:
        # Checked on every resolution, not just in the real translation
        # provider: otherwise a half-filled entry sails through mocked runs
        # (which don't translate for real) and only detonates in production.
        raise ValueError(
            f"{kind.capitalize()} language {code!r} ({lang.name}) is advertised but has no "
            f"FLORES code, so translation would fail at run time. Complete the entry."
        )
    return lang


# Colour per canonical emotion label. Lives here, not in the frontend, so the
# UI never has to keep its own map in sync with what the model emits -- a
# label the backend adds arrives with its colour already decided.
# Values are the palette the editor already uses.
EMOTION_COLORS: dict[str, str] = {
    "neutral": "#8898c8",
    "happiness": "#34d399",
    "anger": "#f87171",
    "sadness": "#818cf8",
    "fear": "#a78bfa",
    "surprise": "#fbbf24",
}
EMOTION_COLOR_FALLBACK = "#8898c8"
