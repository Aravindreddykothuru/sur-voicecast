"""Celery application: one queue per pipeline stage.

Per the PRD: ASR/TTS/emotion/diarization need GPUs, extraction/muxing only
need CPU+ffmpeg, and translation is comparatively cheap. Routing each stage
to its own queue lets you run a small CPU worker fleet alongside a smaller,
expensive GPU fleet, and scale/retry them independently -- see
docker-compose.yml for how the `worker-cpu`, `worker-gpu`, and `worker-tts`
services split these queues across `-Q` flags. `q.synthesize` gets its own
service/image (Dockerfile.worker-tts) rather than sharing `worker-gpu`'s:
CosyVoice2 pins torch==2.3.1 against pyannote/transformers' torch==2.4.1,
and the two cannot coexist in one environment. See requirements-tts.txt and
CONTRACTS.md #1.
"""
from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sur",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.pipeline.tasks", "app.pipeline.regenerate"],
)

# Queue names double as stage names throughout the codebase (events, retries,
# routing) -- keep them in one place.
QUEUE_EXTRACT = "q.extract_audio"
QUEUE_DIARIZE = "q.chunk_and_diarize"
QUEUE_ASR = "q.transcribe"
QUEUE_EMOTION = "q.detect_emotion"
QUEUE_TRANSLATE = "q.translate"
QUEUE_TTS = "q.synthesize"
QUEUE_MUX = "q.mux_export"

STAGE_QUEUES = {
    "extract_audio": QUEUE_EXTRACT,
    "chunk_and_diarize": QUEUE_DIARIZE,
    "transcribe": QUEUE_ASR,
    "detect_emotion": QUEUE_EMOTION,
    "translate": QUEUE_TRANSLATE,
    "synthesize": QUEUE_TTS,
    "mux_export": QUEUE_MUX,
}

celery_app.conf.update(
    task_routes={
        "app.pipeline.tasks.extract_audio": {"queue": QUEUE_EXTRACT},
        "app.pipeline.tasks.chunk_and_diarize": {"queue": QUEUE_DIARIZE},
        "app.pipeline.tasks.transcribe": {"queue": QUEUE_ASR},
        "app.pipeline.tasks.detect_emotion": {"queue": QUEUE_EMOTION},
        "app.pipeline.tasks.translate": {"queue": QUEUE_TRANSLATE},
        "app.pipeline.tasks.synthesize": {"queue": QUEUE_TTS},
        "app.pipeline.tasks.mux_export": {"queue": QUEUE_MUX},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=60 * 60 * 24,
    task_default_retry_delay=10,
    broker_connection_retry_on_startup=True,
)


from celery.exceptions import WorkerShutdown
from celery.signals import worker_init


@worker_init.connect(weak=False)
def _run_startup_checks(**_kwargs):
    """Verify this worker can do the job before it takes any of it.

    Hooked to `worker_init`, not `worker_ready`: worker_ready fires *after* the
    consumer is already pulling from the queue, and raising there only logs --
    the worker carries on and fails jobs one at a time, which is the exact
    outcome these checks exist to avoid. WorkerShutdown from worker_init stops
    the process before a single task is accepted.

    SUR_SKIP_MODEL_CHECKS=1 skips only the slow model-loading half, for
    smoke-testing orchestration on a machine without the weights. The cheap
    capability and secret checks always run. See CONTRACTS.md #1.
    """
    import logging
    import os

    from app.startup_checks import run_worker_startup_checks

    load_models = os.environ.get("SUR_SKIP_MODEL_CHECKS", "").lower() not in ("1", "true", "yes")
    try:
        run_worker_startup_checks(load_models=load_models)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).critical(
            "STARTUP CHECKS FAILED -- refusing to start this worker: %s", exc

        )
        raise WorkerShutdown() from exc
