"""Boot-time verification that this deployment is actually usable.

CONTRACTS.md invariants #1 and #4. Each check is cheap and answers a question
that has silently been "no" in production before:

  * every provider configured as `real` can be constructed, and its model
    loads with a complete head (the emotion classifier ran on random weights
    for a whole release because nothing asked);
  * every gated provider has the credential it needs, named explicitly,
    rather than discovering a 401 midway through a customer's job;
  * every advertised language is complete.

Run by the Celery workers, which are the processes that actually own the
models. The API process calls verify_capabilities() only -- it holds no
models, and booting the API is how an operator would go and look at why the
workers are unhappy.
"""
from __future__ import annotations

import logging

from app.capabilities import SUPPORTED_LANGUAGES, require_language
from app.config import get_settings, hf_token

logger = logging.getLogger(__name__)


class StartupCheckError(RuntimeError):
    """This deployment is misconfigured and must not serve traffic."""


def verify_capabilities() -> None:
    """Every advertised language must be fully specified. Cheap, no models."""
    problems = []
    for lang in SUPPORTED_LANGUAGES:
        try:
            require_language(lang.code)
        except ValueError as e:
            problems.append(str(e))
    if problems:
        raise StartupCheckError(
            "Advertised languages are incomplete: " + "; ".join(problems)
        )
    logger.info("startup: %d target languages verified", len(SUPPORTED_LANGUAGES))


def verify_secrets() -> None:
    """Fail now, with the variable name, rather than on a gated download.

    Scoped to this worker's own queues, exactly like verify_models(): only
    diarization (q.chunk_and_diarize) and translation (q.translate) pull
    gated Hugging Face weights, so a TTS-only worker -- which runs in a
    separate venv and never touches either -- must not be blocked for want of
    a token it will never use.
    """
    settings = get_settings()
    modes = {
        "diarization": ("DIARIZATION_PROVIDER", settings.diarization_provider),
        "translation": ("TRANSLATION_PROVIDER", settings.translation_provider),
    }

    queues = consumed_queues()
    if queues is None:
        relevant = set(modes)  # can't tell -- check every gated provider
    else:
        relevant = {QUEUE_PROVIDERS[q] for q in queues if q in QUEUE_PROVIDERS} & set(modes)

    gated = [modes[name][0] for name in sorted(relevant) if modes[name][1] == "real"]
    if gated and not hf_token():
        raise StartupCheckError(
            f"{', '.join(gated)}=real needs a Hugging Face token (gated weights), but "
            "neither HF_TOKEN nor HUGGING_FACE_HUB_TOKEN is set. Export it before "
            "starting this worker -- it is intentionally not read from .env. "
            "See README 'Rotating the Hugging Face token'."
        )
    if gated:
        logger.info("startup: HF token present for %s", ", ".join(gated))


# Which provider each queue actually needs. A worker only consumes some
# queues, so it only needs some providers -- see verify_models.
QUEUE_PROVIDERS: dict[str, str] = {
    "q.chunk_and_diarize": "diarization",
    "q.transcribe": "asr",
    "q.detect_emotion": "emotion",
    "q.translate": "translation",
    "q.synthesize": "tts",
    # q.extract_audio and q.mux_export are pure ffmpeg -- no model.
}


def consumed_queues() -> set[str] | None:
    """The queues this process was started with (`-Q`), or None if unknown.

    Parsed from argv because that is where the truth is: Celery's config
    doesn't record the -Q override, and each worker in this deployment runs a
    different subset.
    """
    import sys

    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg in ("-Q", "--queues") and i + 1 < len(argv):
            return {q.strip() for q in argv[i + 1].split(",") if q.strip()}
        if arg.startswith("--queues="):
            return {q.strip() for q in arg.split("=", 1)[1].split(",") if q.strip()}
    return None


def verify_models() -> None:
    """Load the models this worker will actually use, now rather than on the
    first customer job.

    Deliberately scoped to the worker's own queues. The TTS provider lives in
    a separate venv and only the q.synthesize worker can import it; demanding
    every worker load every provider made the main worker refuse to start over
    a model it would never touch.

    Each provider's own __init__ runs the fail-loud load and, where it has a
    classification head, the not-degenerate self-check.
    """
    settings = get_settings()
    from app.providers import registry

    getters = {
        "emotion": registry.get_emotion_provider,
        "asr": registry.get_asr_provider,
        "diarization": registry.get_diarization_provider,
        "translation": registry.get_translation_provider,
        "tts": registry.get_tts_provider,
    }
    modes = {
        "emotion": settings.emotion_provider,
        "asr": settings.asr_provider,
        "diarization": settings.diarization_provider,
        "translation": settings.translation_provider,
        "tts": settings.tts_provider,
    }

    queues = consumed_queues()
    if queues is None:
        needed = set(getters)  # can't tell (e.g. embedded) -- check everything
        logger.info("startup: queue set unknown, verifying all real providers")
    else:
        needed = {QUEUE_PROVIDERS[q] for q in queues if q in QUEUE_PROVIDERS}
        logger.info("startup: queues %s -> providers %s", sorted(queues), sorted(needed) or "none")

    failures = []
    for name in sorted(needed):
        if modes[name] != "real":
            continue
        try:
            getters[name]()
            logger.info("startup: %s provider (real) loaded and self-checked", name)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{name}: {e}")
    if failures:
        raise StartupCheckError(
            "Provider(s) configured as real could not be loaded:\n  - "
            + "\n  - ".join(failures)
        )


def run_worker_startup_checks(*, load_models: bool = True) -> None:
    """Called from the Celery worker boot hook. Raising here aborts the
    worker, which is the point: a worker that can't load its models would
    otherwise sit in the queue failing jobs one at a time."""
    verify_capabilities()
    verify_secrets()
    if load_models:
        verify_models()
    logger.info("startup checks passed")
