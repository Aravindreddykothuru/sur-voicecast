"""initial schema -- users, projects, source_videos, speakers, segments, export_jobs

Revision ID: 0001
Revises:
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _guid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("user_id", _guid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("target_languages", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "uploading", "queued", "processing", "ready", "failed",
                name="projectstatus", native_enum=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("preserve_emotion", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("clone_voice", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lip_sync_aware", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tts_model", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "source_videos",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("project_id", _guid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("audio_storage_key", sa.String(1000), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending_upload", "uploaded", "extracted", "failed",
                name="sourcevideostatus", native_enum=False,
            ),
            nullable=False,
            server_default="pending_upload",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_videos_project_id", "source_videos", ["project_id"])

    op.create_table(
        "speakers",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("project_id", _guid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False, server_default="Speaker"),
        sa.Column("diarization_tag", sa.String(100), nullable=True),
        sa.Column("embedding_ref", sa.String(1000), nullable=True),
        sa.Column("reference_clip_url", sa.String(1000), nullable=True),
        sa.Column("consent_captured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_speakers_project_id", "speakers", ["project_id"])

    op.create_table(
        "segments",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("project_id", _guid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_video_id", _guid(), sa.ForeignKey("source_videos.id"), nullable=False),
        sa.Column("speaker_id", _guid(), sa.ForeignKey("speakers.id"), nullable=True),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.String(4000), nullable=True),
        sa.Column("translated_text", sa.String(4000), nullable=True),
        sa.Column(
            "emotion_label",
            sa.Enum(
                "anger", "sadness", "happiness", "fear", "surprise", "neutral",
                name="emotionlabel", native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("emotion_score", sa.Float(), nullable=True),
        sa.Column("emotion_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_audio_url", sa.String(1000), nullable=True),
        sa.Column("tts_audio_url", sa.String(1000), nullable=True),
        sa.Column("tts_duration_ms", sa.Integer(), nullable=True),
        sa.Column("sync_offset_pct", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "transcribed", "emotion_detected", "translated",
                "synthesized", "muxed", "failed",
                name="segmentstatus", native_enum=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_segments_project_id", "segments", ["project_id"])

    op.create_table(
        "export_jobs",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("project_id", _guid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "ready", "failed", name="exportstatus", native_enum=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("format", sa.String(20), nullable=False, server_default="mp4"),
        sa.Column("resolution", sa.String(20), nullable=False, server_default="source"),
        sa.Column("output_url", sa.String(1000), nullable=True),
        sa.Column("qa_report", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_export_jobs_project_id", "export_jobs", ["project_id"])


def downgrade() -> None:
    op.drop_table("export_jobs")
    op.drop_table("segments")
    op.drop_table("speakers")
    op.drop_table("source_videos")
    op.drop_table("projects")
    op.drop_table("users")
