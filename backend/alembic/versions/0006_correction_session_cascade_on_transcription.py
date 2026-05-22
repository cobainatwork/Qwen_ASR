"""Add ON DELETE CASCADE to correction_sessions.transcription_id FK.

When a transcription row is hard-deleted, the database automatically cleans
up all correction_sessions (and via their existing CASCADE, correction_segments)
without requiring explicit application-level deletes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-22

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the unnamed FK created by 0004 (PostgreSQL auto-names it
    # correction_sessions_transcription_id_fkey).
    op.drop_constraint(
        "correction_sessions_transcription_id_fkey",
        "correction_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "correction_sessions_transcription_id_fkey",
        "correction_sessions",
        "transcriptions",
        ["transcription_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "correction_sessions_transcription_id_fkey",
        "correction_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "correction_sessions_transcription_id_fkey",
        "correction_sessions",
        "transcriptions",
        ["transcription_id"],
        ["id"],
    )
