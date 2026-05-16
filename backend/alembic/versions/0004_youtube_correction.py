"""Phase 2 / M9：youtube_downloads / correction_sessions / correction_segments

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "youtube_downloads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("video_title", sa.String(500), nullable=True),
        sa.Column("audio_file_id", sa.Integer(), sa.ForeignKey("audio_files.id"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_youtube_downloads_api_key_id", "youtube_downloads", ["api_key_id"])
    op.create_index("idx_youtube_downloads_status", "youtube_downloads", ["status"])

    op.create_table(
        "correction_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("transcription_id", sa.Integer(), sa.ForeignKey("transcriptions.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="in_progress"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_correction_sessions_api_key_id", "correction_sessions", ["api_key_id"])
    op.create_index("idx_correction_sessions_transcription_id", "correction_sessions", ["transcription_id"])

    op.create_table(
        "correction_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("correction_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_correction_segments_session_id", "correction_segments", ["session_id"])
    op.create_index(
        "idx_correction_segments_session_index_unique",
        "correction_segments",
        ["session_id", "segment_index"],
        unique=True,
    )

    op.execute("CREATE TRIGGER trg_youtube_downloads_updated_at BEFORE UPDATE ON youtube_downloads FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("CREATE TRIGGER trg_correction_sessions_updated_at BEFORE UPDATE ON correction_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("CREATE TRIGGER trg_correction_segments_updated_at BEFORE UPDATE ON correction_segments FOR EACH ROW EXECUTE FUNCTION set_updated_at();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_correction_segments_updated_at ON correction_segments")
    op.execute("DROP TRIGGER IF EXISTS trg_correction_sessions_updated_at ON correction_sessions")
    op.execute("DROP TRIGGER IF EXISTS trg_youtube_downloads_updated_at ON youtube_downloads")
    op.drop_table("correction_segments")
    op.drop_table("correction_sessions")
    op.drop_table("youtube_downloads")
