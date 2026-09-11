"""Provider interface tests using the mock implementations -- no GPU, no
model downloads, exercised the same way the registry would wire them up in
production."""
from __future__ import annotations

from app.providers.base import EmotionResult, SynthesisRequest
from app.providers.asr.mock_provider import MockASRProvider
from app.providers.diarization.mock_provider import MockDiarizationProvider
from app.providers.emotion.mock_provider import MockEmotionProvider
from app.providers.translation.mock_provider import MockTranslationProvider
from app.providers.tts.mock_provider import MockTTSProvider


def test_diarization_provider_splits_and_tags_speakers(tmp_path, monkeypatch):
    # probe_duration_ms shells out to ffprobe; stub it so the test needs no
    # real media file.
    monkeypatch.setattr("app.pipeline.ffmpeg_utils.probe_duration_ms", lambda path: 12000)
    chunks = MockDiarizationProvider().chunk_and_diarize("fake.wav")
    assert len(chunks) >= 3
    assert chunks[0].start_ms == 0
    assert chunks[-1].end_ms == 12000
    tags = {c.speaker_tag for c in chunks}
    assert "SPEAKER_00" in tags


def test_asr_provider_is_deterministic_per_offset():
    provider = MockASRProvider()
    a = provider.transcribe_chunk("fake.wav", 0, 4000)
    b = provider.transcribe_chunk("fake.wav", 0, 4000)
    c = provider.transcribe_chunk("fake.wav", 8000, 12000)
    assert a.text == b.text
    assert a.text != c.text
    assert a.confidence > 0


def test_emotion_provider_cycles_all_labels():
    provider = MockEmotionProvider()
    labels = {provider.detect("fake.wav", i * 4000, i * 4000 + 4000).label for i in range(6)}
    assert labels == {"anger", "sadness", "happiness", "fear", "surprise", "neutral"}


def test_translation_provider_tags_target_language():
    provider = MockTranslationProvider()
    result = provider.translate("Get out of here!", target_lang="te")
    assert result.target_lang == "te"
    assert "[TE]" in result.text
    assert "Get out of here!" in result.text


def test_tts_provider_produces_playable_wav_with_expected_duration(tmp_path):
    provider = MockTTSProvider()
    request = SynthesisRequest(text="hello there", target_lang="te", emotion=EmotionResult(label="anger", score=0.9))
    result = provider.synthesize(request)

    import wave

    with wave.open(result.local_audio_path, "rb") as wf:
        actual_ms = int(1000 * wf.getnframes() / wf.getframerate())
    assert abs(actual_ms - result.duration_ms) <= 1
    assert result.duration_ms > 0


def test_tts_provider_respects_target_duration_hint():
    provider = MockTTSProvider()
    request = SynthesisRequest(text="x", target_lang="te", target_duration_ms=2000)
    result = provider.synthesize(request)
    assert result.duration_ms == 2000
