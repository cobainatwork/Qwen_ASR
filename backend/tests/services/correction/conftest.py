"""Shared fixtures for tests/services/correction/.

_seed_session is used by test_jsonl_exporter, test_excel_exporter, and
test_quality_evaluator.  Centralising it avoids the three near-identical
copies that existed when each test module carried its own private helper.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


def seed_session(
    db: Session,
    *,
    api_key_id: int,
    segments: list[dict],
    audio_filename: str = "seed.wav",
) -> int:
    """Insert audio_file / transcription / correction_session / segments.

    Returns the new correction_session id.  The audio_filename param lets
    callers vary the stored filename so per-test inserts are distinguishable
    in logs (no functional impact).
    """
    db.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size, duration_sec) "
            "VALUES (:a, :fn, '/tmp/test.wav', 1024, 5.0)"
        ),
        {"a": api_key_id, "fn": audio_filename},
    )
    audio_id = int(
        db.execute(
            text(
                "SELECT id FROM audio_files "
                "WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id},
        ).scalar_one()
    )

    db.execute(
        text(
            "INSERT INTO transcriptions "
            "(api_key_id, source, model_name, model_version, transcript_text, duration_sec) "
            "VALUES (:a, 'upload', 'm', 'v1', 'orig', 5.0)"
        ),
        {"a": api_key_id},
    )
    tx_id = int(
        db.execute(
            text(
                "SELECT id FROM transcriptions "
                "WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id},
        ).scalar_one()
    )
    db.execute(
        text("UPDATE audio_files SET transcription_id = :t WHERE id = :a"),
        {"t": tx_id, "a": audio_id},
    )

    db.execute(
        text(
            "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
            "VALUES (:a, :t, 'test-sess')"
        ),
        {"a": api_key_id, "t": tx_id},
    )
    sess_id = int(
        db.execute(
            text(
                "SELECT id FROM correction_sessions "
                "WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id},
        ).scalar_one()
    )

    for s in segments:
        db.execute(
            text(
                "INSERT INTO correction_segments "
                "(session_id, segment_index, start_sec, end_sec, "
                "original_text, corrected_text, speaker_label, is_skipped) "
                "VALUES (:sid, :idx, :st, :en, :orig, :corr, :spk, :skip)"
            ),
            {
                "sid": sess_id,
                "idx": s["index"],
                "st": s["start"],
                "en": s["end"],
                "orig": s["original"],
                "corr": s.get("corrected"),
                "spk": s.get("speaker"),
                "skip": s.get("skipped", False),
            },
        )
    db.commit()
    return sess_id


@pytest.fixture
def correction_service_setup(db_session: Session):
    """Truncate relevant tables and seed one asr:write api_key.

    Returns (db_session, api_key_id).  Each test module that uses this
    fixture gets a clean slate regardless of execution order.
    """
    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, "
            "correction_segments, audio_files CASCADE"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES ('$argon2id$dummy', '1234567890abcdef', 'svc-key', '{asr:write}')"
        )
    )
    api_key_id = int(
        db_session.execute(
            text("SELECT id FROM api_keys WHERE name = 'svc-key'")
        ).scalar_one()
    )
    db_session.commit()
    return db_session, api_key_id
