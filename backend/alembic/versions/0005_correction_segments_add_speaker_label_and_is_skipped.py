"""correction_segments add speaker_label and is_skipped

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "correction_segments",
        sa.Column("speaker_label", sa.Text(), nullable=True),
    )
    op.add_column(
        "correction_segments",
        sa.Column(
            "is_skipped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("correction_segments", "is_skipped")
    op.drop_column("correction_segments", "speaker_label")
