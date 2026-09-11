"""Regression tests for the boot-time guards (CONTRACTS.md #1, #2, #4)."""
from __future__ import annotations

import pytest

from app.config import HF_TOKEN_ENV_VARS, get_settings
from app.startup_checks import (
    StartupCheckError,
    verify_capabilities,
    verify_models,
    verify_secrets,
)


def test_verify_capabilities_passes_on_a_complete_table():
    verify_capabilities()


def test_verify_capabilities_fails_on_an_incomplete_language(monkeypatch):
    """An entry advertised without a FLORES code must stop the boot, not reach
    /api/capabilities and then fail the customer's job."""
    from app import capabilities as caps

    broken = caps.Language("zz", "Broken", "")
    monkeypatch.setattr(caps, "SUPPORTED_LANGUAGES", caps.SUPPORTED_LANGUAGES + (broken,))
    monkeypatch.setitem(caps.LANGUAGES_BY_CODE, "zz", broken)
    # startup_checks imported the names directly; point them at the patched set
    import app.startup_checks as sc
    monkeypatch.setattr(sc, "SUPPORTED_LANGUAGES", caps.SUPPORTED_LANGUAGES)

    with pytest.raises(StartupCheckError, match="incomplete"):
        verify_capabilities()


def test_verify_secrets_passes_when_no_gated_provider_is_real(monkeypatch):
    for var in HF_TOKEN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DIARIZATION_PROVIDER", "mock")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        verify_secrets()
    finally:
        get_settings.cache_clear()


def test_verify_secrets_fails_when_gated_provider_is_real_without_token(monkeypatch):
    """The failure names the variable and the provider -- an operator can act
    on it without reading the source."""
    for var in HF_TOKEN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DIARIZATION_PROVIDER", "real")
    get_settings.cache_clear()
    try:
        with pytest.raises(StartupCheckError) as e:
            verify_secrets()
        msg = str(e.value)
        assert "DIARIZATION_PROVIDER" in msg
        assert "HF_TOKEN" in msg
    finally:
        get_settings.cache_clear()


def test_verify_models_reports_the_failing_provider(monkeypatch):
    """A provider that can't load must abort the boot naming itself."""
    from app.providers import registry

    monkeypatch.setenv("EMOTION_PROVIDER", "real")
    get_settings.cache_clear()

    def _boom():
        raise RuntimeError("head weights missing")

    monkeypatch.setattr(registry, "get_emotion_provider", _boom)
    try:
        with pytest.raises(StartupCheckError) as e:
            verify_models()
        assert "emotion" in str(e.value)
        assert "head weights missing" in str(e.value)
    finally:
        get_settings.cache_clear()


def test_verify_models_is_a_noop_when_everything_is_mock(monkeypatch):
    for var in ("ASR", "DIARIZATION", "TRANSLATION", "EMOTION", "TTS"):
        monkeypatch.setenv(f"{var}_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        verify_models()
    finally:
        get_settings.cache_clear()


def test_worker_refuses_to_boot_when_checks_fail(monkeypatch):
    """The check must STOP the worker, not just log about it.

    Regression: these checks were originally hooked to `worker_ready`, which
    fires after the consumer is already pulling from the queue. The failure was
    logged at CRITICAL and the worker carried on accepting jobs and failing
    them one at a time -- the exact outcome the checks exist to prevent. Only
    a WorkerShutdown raised from `worker_init` actually stops it.
    """
    from celery.exceptions import WorkerShutdown

    from app import celery_app as celery_module

    for var in HF_TOKEN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DIARIZATION_PROVIDER", "real")
    monkeypatch.setenv("SUR_SKIP_MODEL_CHECKS", "1")  # only the cheap half
    get_settings.cache_clear()
    try:
        with pytest.raises(WorkerShutdown):
            celery_module._run_startup_checks()
    finally:
        get_settings.cache_clear()


def test_worker_boots_when_checks_pass(monkeypatch):
    for var in ("ASR", "DIARIZATION", "TRANSLATION", "EMOTION", "TTS"):
        monkeypatch.setenv(f"{var}_PROVIDER", "mock")
    monkeypatch.setenv("SUR_SKIP_MODEL_CHECKS", "1")
    get_settings.cache_clear()
    try:
        from app import celery_app as celery_module

        celery_module._run_startup_checks()  # must not raise
    finally:
        get_settings.cache_clear()


def test_verify_models_only_checks_providers_for_this_workers_queues(monkeypatch):
    """A worker must not refuse to boot over a model it will never use.

    Regression: the TTS provider lives in a separate venv (its torch/numpy pins
    conflict with pyannote's) and only the q.synthesize worker can import it.
    Checking every provider on every worker made the main worker -- which never
    touches TTS -- refuse to start.
    """
    import sys

    from app.providers import registry
    from app.startup_checks import verify_models

    for var in ("ASR", "DIARIZATION", "TRANSLATION", "EMOTION", "TTS"):
        monkeypatch.setenv(f"{var}_PROVIDER", "real")
    get_settings.cache_clear()

    called: list[str] = []
    def _ok(name):
        def _inner():
            called.append(name)
            return object()
        return _inner

    def _tts_boom():
        called.append("tts")
        raise RuntimeError("cosyvoice not installed in this venv")

    monkeypatch.setattr(registry, "get_asr_provider", _ok("asr"))
    monkeypatch.setattr(registry, "get_diarization_provider", _ok("diarization"))
    monkeypatch.setattr(registry, "get_emotion_provider", _ok("emotion"))
    monkeypatch.setattr(registry, "get_translation_provider", _ok("translation"))
    monkeypatch.setattr(registry, "get_tts_provider", _tts_boom)

    # A main worker: every queue except q.synthesize.
    monkeypatch.setattr(
        sys, "argv",
        ["celery", "worker", "-Q", "q.extract_audio,q.transcribe,q.detect_emotion,q.translate,q.mux_export"],
    )
    try:
        verify_models()  # must NOT raise: this worker never synthesises
        assert "tts" not in called, "checked a provider this worker never uses"
        assert {"asr", "emotion", "translation"} <= set(called)

        # The TTS worker, by contrast, must surface the same failure.
        called.clear()
        monkeypatch.setattr(sys, "argv", ["celery", "worker", "-Q", "q.synthesize"])
        with pytest.raises(StartupCheckError, match="tts"):
            verify_models()
    finally:
        get_settings.cache_clear()


def test_verify_secrets_is_scoped_to_this_workers_queues(monkeypatch):
    """The TTS worker runs in its own venv and never does diarization or
    translation, so it must not be blocked for want of an HF token it will
    never use. verify_secrets() is scoped to the -Q queues like verify_models.
    """
    import sys

    for var in HF_TOKEN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DIARIZATION_PROVIDER", "real")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "real")
    get_settings.cache_clear()
    try:
        # TTS-only worker: no gated provider in scope -> passes without a token.
        monkeypatch.setattr(sys, "argv", ["celery", "worker", "-Q", "q.synthesize"])
        verify_secrets()

        # A worker that DOES consume q.translate still fails loudly.
        monkeypatch.setattr(sys, "argv", ["celery", "worker", "-Q", "q.transcribe,q.translate"])
        with pytest.raises(StartupCheckError) as e:
            verify_secrets()
        assert "TRANSLATION_PROVIDER" in str(e.value)
        assert "DIARIZATION_PROVIDER" not in str(e.value)  # not in this worker's scope

        # Unknown queue set (embedded / no -Q) -> checks every gated provider.
        monkeypatch.setattr(sys, "argv", ["python", "-c", "..."])
        with pytest.raises(StartupCheckError) as e2:
            verify_secrets()
        assert "DIARIZATION_PROVIDER" in str(e2.value)
        assert "TRANSLATION_PROVIDER" in str(e2.value)
    finally:
        get_settings.cache_clear()
