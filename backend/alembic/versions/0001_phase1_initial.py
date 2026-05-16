"""Phase 1 初始 schema：api_keys / audio_files / transcriptions / audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # zhparser 擴充
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
    # chinese 中文檢索設定（PostgreSQL 不支援 CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS，故用 DO block）
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese') THEN
                CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
                ALTER TEXT SEARCH CONFIGURATION chinese ADD MAPPING FOR n,v,a,i,e,l WITH simple;
            END IF;
        END $$;
        """
    )

    # api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("lookup_prefix", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default="{asr:read,asr:write}",
        ),
        sa.Column("created_by_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("rate_limit_override", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_api_keys_active_not_deleted",
        "api_keys",
        ["is_active"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_api_keys_lookup_prefix",
        "api_keys",
        ["lookup_prefix"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # transcriptions
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("timestamps", postgresql.JSONB(), nullable=True),
        sa.Column("speakers", postgresql.JSONB(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("post_processing", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="processing"),
        sa.Column("processing_duration_sec", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("hotword_group_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_transcriptions_api_key_id", "transcriptions", ["api_key_id"])
    op.create_index("idx_transcriptions_status", "transcriptions", ["status"])
    op.create_index(
        "idx_transcriptions_created_at",
        "transcriptions",
        [sa.text("created_at DESC")],
    )
    op.create_index("idx_transcriptions_source", "transcriptions", ["source"])
    op.execute(
        "CREATE INDEX idx_transcriptions_text_gin "
        "ON transcriptions USING gin(to_tsvector('chinese', transcript_text))"
    )
    op.execute(
        "CREATE INDEX idx_transcriptions_normalized_text_gin "
        "ON transcriptions USING gin(to_tsvector('chinese', normalized_text))"
    )

    # audio_files
    op.create_table(
        "audio_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("verified_mime_type", sa.String(50), nullable=True),
        sa.Column("transcription_id", sa.Integer(), sa.ForeignKey("transcriptions.id"), nullable=True),
        sa.Column("original_sample_rate", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audio_files_api_key_id", "audio_files", ["api_key_id"])
    op.create_index("idx_audio_files_transcription_id", "audio_files", ["transcription_id"])

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("target_api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_audit_logs_api_key_id_created",
        "audit_logs",
        ["api_key_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_audit_logs_event_type", "audit_logs", ["event_type"])

    # transcriptions.updated_at trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_transcriptions_updated_at
        BEFORE UPDATE ON transcriptions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_transcriptions_updated_at ON transcriptions")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP INDEX IF EXISTS idx_transcriptions_text_gin")
    op.execute("DROP INDEX IF EXISTS idx_transcriptions_normalized_text_gin")
    op.drop_table("audit_logs")
    op.drop_table("audio_files")
    op.drop_table("transcriptions")
    op.drop_table("api_keys")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese")
    op.execute("DROP EXTENSION IF EXISTS zhparser")
