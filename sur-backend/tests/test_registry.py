"""Confirms provider selection is a pure function of config -- the
requirement that swapping a model is an env var flip, not a code change."""
from __future__ import annotations

from app.config import get_settings
from app.providers import registry
from app.providers.asr.mock_provider import MockASRProvider
from app.providers.registry import ProviderNotInstalledError, get_asr_provider


def test_mock_provider_selected_by_default(monkeypatch):
    get_settings.cache_clear()
    registry.get_asr_provider.cache_clear()
    assert isinstance(get_asr_provider(), MockASRProvider)


def test_real_provider_raises_helpful_error_when_uninstalled(monkeypatch):
    """PROVIDER=real without the ML extras must point the operator at
    requirements-ml.txt rather than blowing up with a bare ImportError.

    The import is forced to fail rather than relying on faster-whisper being
    absent: this suite also runs on machines where the real extras *are*
    installed (that's the whole point of requirements-ml.txt), and a test
    whose premise is "the package isn't installed" silently inverts there.
    """
    import builtins

    real_import = builtins.__import__

    def _no_faster_whisper(name, *args, **kwargs):
        if name.startswith("faster_whisper"):
            raise ImportError("faster_whisper not installed (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("ASR_PROVIDER", "real")
    monkeypatch.setattr(builtins, "__import__", _no_faster_whisper)
    get_settings.cache_clear()
    registry.get_asr_provider.cache_clear()
    try:
        registry.get_asr_provider()
        raise AssertionError("expected ProviderNotInstalledError")
    except ProviderNotInstalledError as e:
        assert "requirements-ml.txt" in str(e)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        registry.get_asr_provider.cache_clear()
