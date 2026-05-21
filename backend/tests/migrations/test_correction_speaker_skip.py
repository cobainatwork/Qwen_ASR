"""Migration test: correction_segments add speaker_label + is_skipped.

Fixture dependency chain (all in tests/migrations/conftest.py):
  migration_db_url (module) → migration_engine (module) → mig_session (function)
  alembic_cfg (module)

The migration_engine fixture starts at revision 0004 (baseline before this
migration).  Each test function drives the migration state explicitly.
"""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def test_upgrade_adds_speaker_label_and_is_skipped(
    alembic_cfg: Config, migration_engine: Engine
) -> None:
    """upgrade head must add both columns with correct nullability."""
    command.upgrade(alembic_cfg, "head")

    insp = inspect(migration_engine)
    cols = {c["name"]: c for c in insp.get_columns("correction_segments")}

    assert "speaker_label" in cols, "speaker_label column missing after upgrade"
    assert cols["speaker_label"]["nullable"] is True

    assert "is_skipped" in cols, "is_skipped column missing after upgrade"
    assert cols["is_skipped"]["nullable"] is False


def test_new_segment_defaults(
    alembic_cfg: Config, migration_engine: Engine, mig_session
) -> None:
    """Row inserted without explicit values: speaker_label NULL, is_skipped FALSE."""
    # Ensure we are at head.
    command.upgrade(alembic_cfg, "head")

    with migration_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
                "VALUES ('$argon2id$migtest2', 'migtest2prefix_', 'migtest2-key', '{asr:read}')"
            )
        )
        row_key = conn.execute(
            text("SELECT id FROM api_keys WHERE name = 'migtest2-key'")
        ).first()
        assert row_key is not None
        key_id = int(row_key[0])

        conn.execute(
            text(
                "INSERT INTO audio_files "
                "(api_key_id, storage_path, original_filename, file_size, mime_type, "
                "sample_rate, duration_sec, sha256) "
                "VALUES (:k, '/tmp/mig2.wav', 'mig2.wav', 1000, 'audio/wav', 16000, 1.0, 'def456')"
            ),
            {"k": key_id},
        )
        row_af = conn.execute(
            text("SELECT id FROM audio_files WHERE original_filename = 'mig2.wav'")
        ).first()
        assert row_af is not None
        af_id = int(row_af[0])

        conn.execute(
            text(
                "INSERT INTO transcriptions (api_key_id, audio_file_id, status, model_version) "
                "VALUES (:k, :a, 'completed', 'test')"
            ),
            {"k": key_id, "a": af_id},
        )
        row_tr = conn.execute(
            text("SELECT id FROM transcriptions WHERE audio_file_id = :a"),
            {"a": af_id},
        ).first()
        assert row_tr is not None
        tr_id = int(row_tr[0])

        conn.execute(
            text(
                "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
                "VALUES (:k, :t, 'mig2-test-session')"
            ),
            {"k": key_id, "t": tr_id},
        )
        row_cs = conn.execute(
            text("SELECT id FROM correction_sessions WHERE name = 'mig2-test-session'")
        ).first()
        assert row_cs is not None
        cs_id = int(row_cs[0])

        conn.execute(
            text(
                "INSERT INTO correction_segments "
                "(session_id, segment_index, start_sec, end_sec, original_text) "
                "VALUES (:s, 0, 0.0, 1.0, 'hello')"
            ),
            {"s": cs_id},
        )
        row = conn.execute(
            text(
                "SELECT speaker_label, is_skipped "
                "FROM correction_segments "
                "WHERE session_id = :s AND segment_index = 0"
            ),
            {"s": cs_id},
        ).first()
        assert row is not None
        assert row.speaker_label is None
        assert row.is_skipped is False

        conn.rollback()


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
        # Always restore to head so the module-scoped engine teardown works cleanly.
        command.upgrade(alembic_cfg, "head")
