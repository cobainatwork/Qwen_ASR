"""Migration test: correction_segments add speaker_label + is_skipped.

Fixture strategy:
- In container env (DATABASE_URL set): the entrypoint already ran
  alembic upgrade head, so 0005 is applied. We verify column presence and
  default values against the live schema. The downgrade test is skipped in
  container env to avoid disrupting the production database.
- In local dev (testcontainers): full upgrade + downgrade cycle on an
  isolated DB.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_IN_CONTAINER = bool(os.environ.get("DATABASE_URL", "").strip())


def test_upgrade_adds_speaker_label_and_is_skipped(
    alembic_cfg: Config, migration_engine: Engine
) -> None:
    """After upgrade head, both columns must exist with correct nullability."""
    if not _IN_CONTAINER:
        # Fresh testcontainers DB: start at baseline and upgrade.
        command.upgrade(alembic_cfg, "head")

    insp = inspect(migration_engine)
    cols = {c["name"]: c for c in insp.get_columns("correction_segments")}

    assert "speaker_label" in cols, "speaker_label column missing after upgrade"
    assert cols["speaker_label"]["nullable"] is True

    assert "is_skipped" in cols, "is_skipped column missing after upgrade"
    assert cols["is_skipped"]["nullable"] is False


def test_new_segment_defaults(
    alembic_cfg: Config, migration_engine: Engine
) -> None:
    """Row inserted without explicit values: speaker_label NULL, is_skipped FALSE."""
    if not _IN_CONTAINER:
        command.upgrade(alembic_cfg, "head")

    with migration_engine.connect() as conn:
        # Seed: api_key
        conn.execute(
            text(
                "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
                "VALUES ('$argon2id$migtest3', 'migtest3prefix_', 'migtest3-key', '{asr:read}')"
                " ON CONFLICT DO NOTHING"
            )
        )
        row_key = conn.execute(
            text("SELECT id FROM api_keys WHERE name = 'migtest3-key'")
        ).first()
        assert row_key is not None
        key_id = int(row_key[0])

        # Seed: transcription (no audio_file required — nullable FK).
        conn.execute(
            text(
                "INSERT INTO transcriptions "
                "(api_key_id, source, model_name, model_version, status) "
                "VALUES (:k, 'upload', 'Qwen3-ASR-1.7B', 'test', 'completed')"
            ),
            {"k": key_id},
        )
        row_tr = conn.execute(
            text(
                "SELECT id FROM transcriptions "
                "WHERE api_key_id = :k AND model_version = 'test' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"k": key_id},
        ).first()
        assert row_tr is not None
        tr_id = int(row_tr[0])

        # Seed: correction_session
        conn.execute(
            text(
                "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
                "VALUES (:k, :t, 'mig3-test-session')"
            ),
            {"k": key_id, "t": tr_id},
        )
        row_cs = conn.execute(
            text("SELECT id FROM correction_sessions WHERE name = 'mig3-test-session'")
        ).first()
        assert row_cs is not None
        cs_id = int(row_cs[0])

        # Seed: correction_segment without explicit speaker_label / is_skipped.
        conn.execute(
            text(
                "INSERT INTO correction_segments "
                "(session_id, segment_index, start_sec, end_sec, original_text) "
                "VALUES (:s, 99, 0.0, 1.0, 'mig3-hello')"
            ),
            {"s": cs_id},
        )
        row = conn.execute(
            text(
                "SELECT speaker_label, is_skipped "
                "FROM correction_segments "
                "WHERE session_id = :s AND segment_index = 99"
            ),
            {"s": cs_id},
        ).first()
        assert row is not None
        assert row.speaker_label is None
        assert row.is_skipped is False

        conn.rollback()


@pytest.mark.skipif(
    _IN_CONTAINER,
    reason="Downgrade test skipped in container env to protect the live production DB.",
)
def test_downgrade_removes_columns(
    alembic_cfg: Config, migration_engine: Engine
) -> None:
    """downgrade -1 must drop both columns; re-upgrade restores them."""
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "-1")
    try:
        insp = inspect(migration_engine)
        cols = {c["name"] for c in insp.get_columns("correction_segments")}
        assert "speaker_label" not in cols, "speaker_label should be gone after downgrade"
        assert "is_skipped" not in cols, "is_skipped should be gone after downgrade"
    finally:
        command.upgrade(alembic_cfg, "head")
