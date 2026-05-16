"""Phase 2 / M5：hotword_groups / hotwords / datasets / dataset_samples

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hotword_groups
    op.create_table(
        "hotword_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_hotword_groups_api_key_id", "hotword_groups", ["api_key_id"])

    # hotwords
    op.create_table(
        "hotwords",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("hotword_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("word", sa.String(100), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pinyin", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_hotwords_group_id", "hotwords", ["group_id"])

    # datasets
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_datasets_api_key_id", "datasets", ["api_key_id"])

    # dataset_samples
    op.create_table(
        "dataset_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audio_file_id", sa.Integer(), sa.ForeignKey("audio_files.id"), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_dataset_samples_dataset_id", "dataset_samples", ["dataset_id"])

    # updated_at trigger（複用 0001 既有 set_updated_at function）
    op.execute("CREATE TRIGGER trg_hotword_groups_updated_at BEFORE UPDATE ON hotword_groups FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("CREATE TRIGGER trg_datasets_updated_at BEFORE UPDATE ON datasets FOR EACH ROW EXECUTE FUNCTION set_updated_at();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_datasets_updated_at ON datasets")
    op.execute("DROP TRIGGER IF EXISTS trg_hotword_groups_updated_at ON hotword_groups")
    op.drop_table("dataset_samples")
    op.drop_table("datasets")
    op.drop_table("hotwords")
    op.drop_table("hotword_groups")
