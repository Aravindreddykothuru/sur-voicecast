"""Centralized, .env-driven configuration.

Every knob that differs between local dev, CI, and production lives here --
nothing else in the codebase should call os.environ directly. This is what
makes the "run without a GPU" and "swap a provider" requirements possible
without touching pipeline code.
"""
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

ProviderMode = Literal["mock", "real"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "sur-backend"
    environment: str = "development"
    log_level: str = "INFO"
    api_cors_origins: str = "http://localhost:3000"

    # --- Database ---
    database_url: str = "postgresql+psycopg2://sur:sur@localhost:5432/sur"
    async_database_url: str = "postgresql+asyncpg://sur:sur@localhost:5432/sur"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- Object storage ---
    storage_backend: str = "local"  # "local" or "s3"
    # None means "use the real AWS S3 endpoint for storage_region" -- boto3's
    # own client() treats endpoint_url=None as "no override" natively. Only
    # set an explicit http://... value when pointing at MinIO, R2, or another
    # S3-compatible store that isn't AWS itself.
    storage_endpoint_url: str | None = None
    storage_public_endpoint_url: str | None = None
    storage_access_key: str = "sur_minio"
    storage_secret_key: str = "sur_minio_secret"
    storage_bucket: str = "sur-media"
    storage_region: str = "us-east-1"
    storage_use_ssl: bool = False

    # --- Providers ---
    asr_provider: ProviderMode = "mock"
    diarization_provider: ProviderMode = "mock"
    translation_provider: ProviderMode = "mock"
    emotion_provider: ProviderMode = "mock"
    tts_provider: ProviderMode = "mock"

    # NOTE: hf_token is deliberately NOT a Settings field. A long-lived
    # credential must not live in a file next to the code -- see hf_token()
    # below, which reads it from the process environment at call time.

    asr_model_name: str = "large-v3"
    asr_device: str = "cpu"
    # Source language for ASR. "auto" lets Whisper detect it per chunk, which
    # is what a dubbing tool wants -- pinning it to "en" (as this used to)
    # forces every non-English source to be decoded as English. Set an
    # explicit code (e.g. "en", "hi") when the source language is known, since
    # that's both faster and more accurate than detection on short chunks.
    asr_language: str = "auto"
    # One model per IndicTrans2 direction, loaded lazily by whichever
    # (source, target) pair actually shows up -- a run that never dubs a
    # non-English source never pays to download indic-en/indic-indic.
    # translation_src_lang was removed: it hardcoded every source as English
    # regardless of what ASR detected, which is the exact bug that let a
    # 98%-confidence Chinese detection get silently translated as English.
    # See CONTRACTS.md #3 and #5.
    translation_model_name: str = "ai4bharat/indictrans2-en-indic-1B"
    translation_indic_en_model_name: str = "ai4bharat/indictrans2-indic-en-1B"
    translation_indic_indic_model_name: str = "ai4bharat/indictrans2-indic-indic-1B"
    tts_model_name: str = "cosyvoice2"
    tts_device: str = "cpu"
    # Must be a checkpoint whose classification head actually loads under the
    # installed transformers. Two earlier picks failed that bar:
    # audeering/...-24-ft-... doesn't exist on the Hub, and
    # ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition stores its head
    # as classifier.dense/classifier.output, which today's
    # Wav2Vec2ForSequenceClassification ignores -- so it silently loaded with a
    # RANDOM head and emitted noise at ~chance confidence. SUPERB's ER models
    # use the standard head and load cleanly (verified by loading twice and
    # comparing classifier.weight). Trade-off: IEMOCAP's 4 labels only
    # (neutral/happy/angry/sad), so fear and surprise are never predicted.
    # superb/hubert-large-superb-er is a drop-in, more accurate, slower swap.
    emotion_model_name: str = "superb/wav2vec2-base-superb-er"

    # Emotion predictions below this confidence are shown as "uncertain"
    # rather than as a label. One number, served via /api/capabilities, so the
    # UI never hardcodes its own threshold.
    emotion_confidence_floor: float = 0.4

    # --- Pipeline ---
    default_target_language: str = "te"
    sync_tolerance_pct: float = 10.0

    # --- Upload limits ---
    # Enforced server-side (routes_projects.py), not just advisory copy in the
    # UI: an upload whose content_type isn't listed here, or whose confirmed
    # size exceeds this, is rejected rather than silently accepted and failing
    # deep in the pipeline later. Served via /api/capabilities so the UI's
    # file picker can't offer a choice the backend will then refuse.
    max_upload_mb: int = 2048
    accepted_video_formats: str = "video/mp4,video/quicktime,video/x-matroska,video/webm"

    @property
    def accepted_video_format_list(self) -> list[str]:
        return [f.strip() for f in self.accepted_video_formats.split(",") if f.strip()]

    @property
    def compute_device(self) -> str:
        """Single honest device summary for /api/capabilities' Runtime panel.

        Derived from the configured per-stage device settings, not a live
        torch.cuda.is_available() probe: the API process doesn't necessarily
        have torch installed (it isn't in requirements.txt, only
        requirements-ml.txt/-tts.txt, which run in the worker containers) and
        even if it did, the API's own hardware isn't necessarily the worker's.
        Reports "cuda" only if every real-provider device knob actually asks
        for it -- a mixed deployment (e.g. ASR on GPU, TTS still on CPU)
        reports "cpu" so ETA estimates stay conservative rather than
        overpromising. See CONTRACTS.md #5 (no silent defaults / no
        optimistic guessing).
        """
        return "cuda" if self.asr_device == "cuda" and self.tts_device == "cuda" else "cpu"

    @property
    def asr_autodetect(self) -> bool:
        return self.asr_language == "auto"

    # Hosts that hold real user data. A process that is not explicitly
    # ENVIRONMENT=production must never open a connection to one of these.
    # This is a crash, not a warning, because the convention "don't point
    # your local .env at prod" already failed once: migrations were applied
    # and rows were deleted against the database holding real users during a
    # debugging session, because dev and prod were the same instance.
    production_db_hosts: str = "pooler.supabase.com,db.bwwdpjkdxmgfdlyffgzr.supabase.co"

    @property
    def production_db_host_list(self) -> list[str]:
        return [h.strip() for h in self.production_db_hosts.split(",") if h.strip()]

    @model_validator(mode="after")
    def _refuse_production_database_outside_production(self) -> "Settings":
        if self.environment.strip().lower() == "production":
            return self
        host = (make_url(self.database_url).host or "").lower()
        for prod_host in self.production_db_host_list:
            if prod_host.lower() in host:
                raise RuntimeError(
                    f"REFUSING TO START: DATABASE_URL points at the production host "
                    f"{host!r} but ENVIRONMENT={self.environment!r}, not 'production'.\n"
                    "This process would read and write real user data. Point "
                    "DATABASE_URL at your dev database (see docker-compose.test.yml "
                    "or a second Supabase project), or set ENVIRONMENT=production if "
                    "this really is the production deployment.\n"
                    "Production credentials belong in deploy config, never in a local .env."
                )
        return self

    # --- Auth ---
    # Falls back to the X-User-Email dev stub (app/core/security.py) when no
    # request carries a real bearer token -- keeps every existing route and
    # test working unchanged while /api/auth/{signup,login} issue real,
    # password-verified tokens for anyone who goes through them.
    dev_default_user_email: str = "dev@sur.local"
    # A real deployment MUST override this (env var, not this default) --
    # anyone who knows it can forge a valid token for any user id. Kept as a
    # plain default (not a hard-fail) only because this is still a
    # single-user local dev tool; see CONTRACTS.md #4 for the same rule
    # already enforced for HF_TOKEN.
    jwt_secret_key: str = "dev-only-insecure-secret-override-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
# Read from the process environment at call time, never persisted to .env and
# never cached in Settings, so rotating the token is a restart rather than an
# edit-and-redeploy, and a stale value can't linger in a cached object.
# See CONTRACTS.md invariant #4 and README "Rotating the Hugging Face token".
HF_TOKEN_ENV_VARS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


def hf_token() -> str | None:
    """The Hugging Face token, or None if unset. Callers that require it should
    use require_hf_token() so the failure names the variable to set."""
    import os

    for var in HF_TOKEN_ENV_VARS:
        value = os.environ.get(var)
        if value and value.strip():
            return value.strip()
    return None


def require_hf_token(reason: str) -> str:
    """Fail with an actionable message rather than letting a gated download
    return an opaque 401. CONTRACTS.md #3: never substitute a silent default."""
    token = hf_token()
    if not token:
        raise RuntimeError(
            f"{reason} requires a Hugging Face token, but none of "
            f"{', '.join(HF_TOKEN_ENV_VARS)} is set in the environment. "
            "Create one at https://huggingface.co/settings/tokens (read scope), "
            "accept the gated model's licence with that account, then export it "
            "before starting the worker. It is intentionally not read from .env."
        )
    return token
