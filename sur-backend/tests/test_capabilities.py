"""Regression tests for CONTRACTS.md invariant #2 (single source of truth).

The bug these exist to prevent: the frontend offered 12 target languages
while the translation provider had FLORES codes for 7. Choosing one of the
other 5 raised ValueError inside the translate stage and failed the project.
Two lists, no test tying them together.
"""
from __future__ import annotations

import pytest

from app.capabilities import (
    FLORES_CODES,
    LANGUAGES_BY_CODE,
    SUPPORTED_LANGUAGES,
    require_language,
)


def test_every_supported_language_has_a_flores_code():
    """THE test that would have caught the original bug.

    Adding a language to SUPPORTED_LANGUAGES without a FLORES mapping now
    fails the build instead of failing a customer's job.
    """
    missing = [lang.code for lang in SUPPORTED_LANGUAGES if not lang.flores]
    assert not missing, f"languages offered with no FLORES mapping: {missing}"


def test_every_supported_language_has_a_display_name():
    missing = [lang.code for lang in SUPPORTED_LANGUAGES if not lang.name]
    assert not missing, f"languages with no display name: {missing}"


def test_language_codes_are_unique():
    codes = [lang.code for lang in SUPPORTED_LANGUAGES]
    assert len(codes) == len(set(codes)), f"duplicate language codes in {codes}"


def test_flores_map_is_derived_not_duplicated():
    assert FLORES_CODES == {l.code: l.flores for l in SUPPORTED_LANGUAGES}
    assert set(FLORES_CODES) == set(LANGUAGES_BY_CODE)


def test_unknown_language_raises_rather_than_defaulting():
    """CONTRACTS.md #3: never substitute a silent default."""
    with pytest.raises(ValueError, match="Unsupported target language"):
        require_language("xx")


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES, ids=lambda l: l.code)
def test_translation_providers_accept_every_supported_language(lang):
    """Both providers must accept exactly what capabilities advertises."""
    from app.providers.translation.mock_provider import MockTranslationProvider

    result = MockTranslationProvider().translate("hello", target_lang=lang.code)
    assert result.target_lang == lang.code

    # The real provider is not instantiated here (it needs 4GB of weights), but
    # its language resolution is the same require_language() call, exercised
    # directly so an unmapped language still fails this test.
    assert require_language(lang.code).flores == lang.flores


def test_capabilities_endpoint_lists_languages_and_emotions(client):
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    body = resp.json()

    assert [l["code"] for l in body["languages"]] == [l.code for l in SUPPORTED_LANGUAGES]
    for entry in body["languages"]:
        assert entry["display_name"], "every language must carry a display name"
        assert entry["flores_code"], "frontend needs this to distinguish real dub targets, not just tts_available"
        assert "tts_available" in entry

    # Emotion labels are derived from the provider, not hardcoded in the route,
    # and each arrives with its colour so the UI keeps no map of its own.
    from app.providers.registry import get_emotion_provider

    assert [e["label"] for e in body["emotions"]] == get_emotion_provider().available_labels()
    for entry in body["emotions"]:
        assert entry["color"].startswith("#"), f"no colour for {entry['label']}"

    # index must be the entry's own position -- the frontend maps index ->
    # CSS custom property (--emo-1..4) rather than keying off the label
    # string, so a swapped or renamed label can't silently point at the
    # wrong color slot.
    assert [e["index"] for e in body["emotions"]] == list(range(len(body["emotions"])))

    assert set(body["providers"]) == {"asr", "diarization", "translation", "emotion", "tts"}
    # The uncertainty floor is served, not a frontend constant.
    assert 0.0 <= body["emotion_confidence_floor"] <= 1.0

    # Runtime-panel and upload-gating fields: all real Settings-derived
    # values, not client-invented defaults. See CONTRACTS.md #2 and #5.
    assert body["device"] in ("cpu", "cuda")
    assert isinstance(body["asr_autodetect"], bool)
    assert body["max_upload_mb"] > 0
    assert body["accepted_formats"], "must list at least one accepted format"
    assert all(f.startswith("video/") for f in body["accepted_formats"])


def test_emotion_labels_are_derived_from_the_provider():
    """CONTRACTS.md #2 for emotions: the label list must come from the model."""
    from app.providers.emotion.mock_provider import MockEmotionProvider

    labels = MockEmotionProvider().available_labels()
    assert labels, "provider must report the labels it can emit"
    # Every advertised label must be one the provider can actually return.
    emitted = {
        MockEmotionProvider().detect("x.wav", i * 4000, i * 4000 + 4000).label
        for i in range(len(labels))
    }
    assert emitted == set(labels)


@pytest.mark.parametrize(
    "asr_device,tts_device,expected",
    [("cpu", "cpu", "cpu"), ("cuda", "cpu", "cpu"), ("cpu", "cuda", "cpu"), ("cuda", "cuda", "cuda")],
)
def test_compute_device_is_conservative_not_optimistic(monkeypatch, asr_device, tts_device, expected):
    """A mixed deployment (one stage still on CPU) must report "cpu", not
    "cuda" -- overpromising a fast device would make the Runtime panel's ETA
    copy actively wrong instead of just missing. See CONTRACTS.md #5."""
    from app.config import get_settings

    monkeypatch.setenv("ASR_DEVICE", asr_device)
    monkeypatch.setenv("TTS_DEVICE", tts_device)
    get_settings.cache_clear()
    try:
        assert get_settings().compute_device == expected
    finally:
        get_settings.cache_clear()
