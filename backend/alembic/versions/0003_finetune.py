"""Phase 2 / M8：finetune_tasks / finetune_checkpoints

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-17

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finetune_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("base_model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("loss_history", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_finetune_tasks_api_key_id", "finetune_tasks", ["api_key_id"])
    op.create_index("idx_finetune_tasks_status", "finetune_tasks", ["status"])

    op.create_table(
        "finetune_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("finetune_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("loss", sa.Float(), nullable=False),
        sa.Column("wer", sa.Float(), nullable=True),
        sa.Column("checkpoint_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_finetune_checkpoints_task_id", "finetune_checkpoints", ["task_id"])
    # 唯一 active checkpoint per task（partial unique index）
    op.create_index(
        "idx_finetune_checkpoints_active_unique",
        "finetune_checkpoints",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.execute(
        "CREATE TRIGGER trg_finetune_tasks_updated_at "
        "BEFORE UPDATE ON finetune_tasks FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_finetune_tasks_updated_at ON finetune_tasks")
    op.drop_table("finetune_checkpoints")
    op.drop_table("finetune_tasks")
