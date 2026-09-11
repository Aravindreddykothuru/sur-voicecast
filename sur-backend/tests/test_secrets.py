"""Regression tests for CONTRACTS.md invariant #4 (secrets never on disk)."""
from __future__ import annotations

import pathlib

import pytest

from app.config import HF_TOKEN_ENV_VARS, hf_token, require_hf_token

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("filename", [".env", ".env.example"])
def test_no_hf_token_value_is_committed_to_disk(filename):
    """A token in .env outlives the session that created it and gets copied
    around. It must be supplied by the environment instead."""
    path = BACKEND_ROOT / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        assert key.strip() not in HF_TOKEN_ENV_VARS or not value.strip(), (
            f"{filename} assigns {key.strip()} a value; secrets must come from "
            "the process environment (CONTRACTS.md #4)"
        )


def test_no_hf_token_literal_anywhere_in_repo():
    """Catches a token pasted into any tracked source file, not just .env."""
    offenders = []
    for path in BACKEND_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".env", ".example", ".md", ".yml", ".yaml", ".toml"}:
            continue
        if any(part in {".venv", ".venv-tts", ".tools", "__pycache__", ".git"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # A real token is "hf_" + 34 alphanumerics; the prefix alone is fine
        # to mention in prose.
        import re
        if re.search(r"\bhf_[A-Za-z0-9]{30,}\b", text):
            offenders.append(str(path.relative_to(BACKEND_ROOT)))
    assert not offenders, f"Hugging Face token literal found in: {offenders}"


def test_require_hf_token_raises_actionably_when_unset(monkeypatch):
    """CONTRACTS.md #3: raise, don't silently proceed to an opaque 401."""
    for var in HF_TOKEN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    assert hf_token() is None
    with pytest.raises(RuntimeError) as e:
        require_hf_token("DIARIZATION_PROVIDER=real (pyannote)")
    msg = str(e.value)
    assert "HF_TOKEN" in msg
    assert "huggingface.co/settings/tokens" in msg
    assert "not read from .env" in msg


def test_token_is_read_from_environment_at_call_time(monkeypatch):
    """Rotation must be a restart, not a code change: no caching."""
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    monkeypatch.setenv("HF_TOKEN", "hf_first")
    assert require_hf_token("x") == "hf_first"
    monkeypatch.setenv("HF_TOKEN", "hf_second")
    assert require_hf_token("x") == "hf_second", "token was cached; rotation would not take effect"


def test_alternate_env_var_is_honoured(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HUGGING_FACE_HUB_TOKEN", "hf_alt")
    assert hf_token() == "hf_alt"
