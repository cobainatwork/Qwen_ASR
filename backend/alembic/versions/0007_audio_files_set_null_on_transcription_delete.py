"""audio_files.transcription_id SET NULL on transcription delete

Migration 0006 added ON DELETE CASCADE to correction_sessions.transcription_id
but missed audio_files.transcription_id reverse FK. DELETE transcription
crashed with ForeignKeyViolation in production.

This migration sets the FK to ON DELETE SET NULL — preserves audio_file row
(design intent: audio_file may be reused for re-transcription) while allowing
transcription to be deleted cleanly.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-22

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "audio_files_transcription_id_fkey",
        "audio_files",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audio_files_transcription_id_fkey",
        "audio_files",
        "transcriptions",
        ["transcription_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "audio_files_transcription_id_fkey",
        "audio_files",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audio_files_transcription_id_fkey",
        "audio_files",
        "transcriptions",
        ["transcription_id"],
        ["id"],
    )
