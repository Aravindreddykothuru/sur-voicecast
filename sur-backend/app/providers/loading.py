"""Fail-loud model loading.

Why this exists: `transformers.from_pretrained` treats a checkpoint whose
keys don't match the architecture as a *success*. It logs a warning and
silently random-initialises whatever it couldn't fill in. That is how
ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition shipped here for a
whole release: its head is stored as `classifier.dense`/`classifier.output`,
today's `Wav2Vec2ForSequenceClassification` wants
`projector.*`/`classifier.*`, so the emotion model ran on a RANDOM head and
emitted noise at chance confidence. Nothing failed. Nothing alerted.

Every model load in this codebase goes through here instead, and any missing
weight that isn't on the explicit benign allowlist is a hard error.

See CONTRACTS.md, invariant #1.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class ModelLoadError(RuntimeError):
    """A model could not be loaded with all of its trained weights intact."""


# Keys that name a classification/projection head. If any of these is missing
# from a checkpoint the model is not the model you think it is -- its
# predictions are random. Never tolerated.
_HEAD_KEY_RE = re.compile(r"(^|\.)(classifier|projector|score|head|out_proj)(\.|$)")

# The ONLY missing keys tolerated, and only because they are a documented
# rename rather than absent training: PyTorch moved weight-norm from
# `weight_g`/`weight_v` to the `parametrizations.weight.original0/1` form, so
# every wav2vec2/hubert checkpoint saved before that switch reports the new
# names as "missing" while carrying the old ones as "unexpected". The values
# are present and identical -- only the spelling changed. Anything not
# matching this stays fatal.
_BENIGN_MISSING_RE = re.compile(
    r"encoder\.pos_conv_embed\.conv\.parametrizations\.weight\.original[01]$"
)


def _classify(keys: list[str]) -> tuple[list[str], list[str]]:
    """Split missing keys into (head_keys, other_non_benign_keys)."""
    head = [k for k in keys if _HEAD_KEY_RE.search(k)]
    other = [k for k in keys if k not in head and not _BENIGN_MISSING_RE.search(k)]
    return head, other


def load_hf_model(loader, model_name: str, **kwargs):
    """Load a transformers model, refusing anything with an incomplete head.

    `loader` is the class to call, e.g. AutoModelForAudioClassification.
    Returns the model. Raises ModelLoadError if weights are missing.
    """
    model, info = loader.from_pretrained(model_name, output_loading_info=True, **kwargs)

    missing = list(info.get("missing_keys") or [])
    unexpected = list(info.get("unexpected_keys") or [])
    mismatched = list(info.get("mismatched_keys") or [])

    head_missing, other_missing = _classify(missing)

    problems = []
    if head_missing:
        problems.append(
            f"classification head weights were NOT in the checkpoint and would be "
            f"randomly initialised: {sorted(head_missing)}. The checkpoint carries "
            f"{sorted(k for k in unexpected if _HEAD_KEY_RE.search(k)) or 'no head keys'} "
            f"instead -- this architecture cannot use it."
        )
    if other_missing:
        problems.append(f"weights missing from checkpoint: {sorted(other_missing)}")
    if mismatched:
        problems.append(f"weights with mismatched shapes: {mismatched}")

    if problems:
        raise ModelLoadError(
            f"Refusing to use '{model_name}': " + "; ".join(problems) +
            ". Pick a checkpoint whose head matches this architecture, or add an "
            "explicit remapping. See CONTRACTS.md invariant #1."
        )

    if unexpected:
        # Not fatal: extra keys mean the checkpoint carries things this
        # architecture doesn't need. Worth seeing, not worth refusing.
        logger.info("%s: ignoring %d unexpected checkpoint keys", model_name, len(unexpected))
    return model


def assert_not_degenerate(probabilities, model_name: str, *, tolerance: float = 0.05) -> None:
    """Reject a model whose output is indistinguishable from a coin toss.

    A randomly-initialised head doesn't just mispredict, it produces a
    near-uniform distribution over labels. Loading checks catch the known
    shape of that failure; this catches the *behaviour* regardless of cause.
    """
    probs = [float(p) for p in probabilities]
    if not probs:
        raise ModelLoadError(f"{model_name} produced no output for the self-check sample")
    uniform = 1.0 / len(probs)
    if max(probs) - uniform < tolerance:
        raise ModelLoadError(
            f"Refusing to use '{model_name}': on the built-in self-check sample its "
            f"most confident label scored {max(probs):.3f}, barely above the "
            f"{uniform:.3f} you'd get from random weights (tolerance {tolerance}). "
            "This is what an unloaded/random head looks like. See CONTRACTS.md invariant #1."
        )
