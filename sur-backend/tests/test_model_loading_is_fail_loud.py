"""Regression tests for CONTRACTS.md invariant #1 (fail-loud model loading).

The bug these exist to prevent: the emotion classifier shipped for a full
release running on a RANDOM head, because transformers silently
random-initialises keys it can't find in a checkpoint and returns a model
that looks fine. Confidence sat at chance (0.14 over 8 labels) and nothing
failed.

Both tests below fail against the pre-fix code path.
"""
from __future__ import annotations

import pytest

from app.providers.loading import ModelLoadError, assert_not_degenerate, load_hf_model


class _FakeLoader:
    """Stands in for AutoModelForAudioClassification.from_pretrained so these
    tests need no network and no weights."""

    def __init__(self, missing=(), unexpected=(), mismatched=()):
        self._info = {
            "missing_keys": list(missing),
            "unexpected_keys": list(unexpected),
            "mismatched_keys": list(mismatched),
        }

    def from_pretrained(self, name, output_loading_info=False, **kwargs):
        model = object()
        return (model, self._info) if output_loading_info else model


def test_rejects_checkpoint_whose_head_is_missing():
    """This is verbatim the ehcalabres failure that shipped."""
    loader = _FakeLoader(
        missing=[
            "classifier.bias", "classifier.weight",
            "projector.bias", "projector.weight",
            "wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0",
        ],
        unexpected=[
            "classifier.dense.bias", "classifier.dense.weight",
            "classifier.output.bias", "classifier.output.weight",
        ],
    )
    with pytest.raises(ModelLoadError) as e:
        load_hf_model(loader, "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition")
    msg = str(e.value)
    assert "randomly initialised" in msg
    assert "classifier.weight" in msg


def test_accepts_checkpoint_missing_only_the_weight_norm_rename():
    """The good model (superb/*) reports the same benign pair as missing.

    Guards the fix against over-correction: a blanket "raise on any missing
    key" would reject every pre-2024 wav2vec2/hubert checkpoint, including
    the working one.
    """
    loader = _FakeLoader(
        missing=[
            "wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0",
            "wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original1",
        ],
        unexpected=[
            "wav2vec2.encoder.pos_conv_embed.conv.weight_g",
            "wav2vec2.encoder.pos_conv_embed.conv.weight_v",
        ],
    )
    assert load_hf_model(loader, "superb/wav2vec2-base-superb-er") is not None


def test_rejects_mismatched_shapes():
    loader = _FakeLoader(mismatched=[("classifier.weight", (4, 256), (8, 256))])
    with pytest.raises(ModelLoadError, match="mismatched"):
        load_hf_model(loader, "some/model")


def test_rejects_non_head_missing_weights():
    loader = _FakeLoader(missing=["wav2vec2.encoder.layers.3.attention.k_proj.weight"])
    with pytest.raises(ModelLoadError, match="missing from checkpoint"):
        load_hf_model(loader, "some/model")


@pytest.mark.parametrize(
    "probs, should_raise",
    [
        ([0.25, 0.25, 0.25, 0.25], True),    # perfectly uniform -> random head
        ([0.26, 0.25, 0.25, 0.24], True),    # what the broken model actually did
        ([0.63, 0.23, 0.13, 0.01], False),   # what the fixed model actually does
        ([0.98, 0.01, 0.01, 0.00], False),
    ],
)
def test_degenerate_output_is_rejected(probs, should_raise):
    if should_raise:
        with pytest.raises(ModelLoadError, match="random weights"):
            assert_not_degenerate(probs, "test/model")
    else:
        assert_not_degenerate(probs, "test/model")


def test_empty_output_is_rejected():
    with pytest.raises(ModelLoadError, match="no output"):
        assert_not_degenerate([], "test/model")
