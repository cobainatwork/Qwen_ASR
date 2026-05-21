"""JSONL 匯出：排除 is_skipped 與 corrected_text=NULL 的段落。

Self-contained fixture — follows project pattern (test_correction_router.py).
"""
from __future__ import annotations

import json

import pytest
from app.services.correction.jsonl_exporter import session_to_jsonl
from sqlalchemy import text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_session(
    db: Session,
    *,
    api_key_id: int,
    segments: list[dict],
) -> int:
    """建立 transcription / audio_file / correction_session / segments，回傳 session_id。"""
    db.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size, duration_sec) "
            "VALUES (:a, 'seed.wav', '/tmp/seed.wav', 1024, 5.0)"
        ),
        {"a": api_key_id},
    )
    audio_id = int(db.execute(
        text("SELECT id FROM audio_files WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": api_key_id},
    ).scalar_one())

    db.execute(
        text(
            "INSERT INTO transcriptions "
            "(api_key_id, source, model_name, model_version, transcript_text, duration_sec) "
            "VALUES (:a, 'upload', 'm', 'v1', 'orig', 5.0)"
        ),
        {"a": api_key_id},
    )
    tx_id = int(db.execute(
        text("SELECT id FROM transcriptions WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": api_key_id},
    ).scalar_one())
    db.execute(
        text("UPDATE audio_files SET transcription_id = :t WHERE id = :a"),
        {"t": tx_id, "a": audio_id},
    )

    db.execute(
        text(
            "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
            "VALUES (:a, :t, 'jsonl-test')"
        ),
        {"a": api_key_id, "t": tx_id},
    )
    sess_id = int(db.execute(
        text("SELECT id FROM correction_sessions WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": api_key_id},
    ).scalar_one())

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def jsonl_setup(db_session: Session, seed_api_key: int):
    """回傳 (db_session, api_key_id)，TRUNCATE 確保乾淨環境。"""
    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, "
            "correction_segments, audio_files CASCADE"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES ('$argon2id$dummy', '1234567890abcdef', 'jsonl-key', '{asr:write}')"
        )
    )
    api_key_id = int(db_session.execute(
        text("SELECT id FROM api_keys WHERE name = 'jsonl-key'")
    ).scalar_one())
    db_session.commit()
    return db_session, api_key_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_session_to_jsonl_includes_only_corrected(jsonl_setup) -> None:
    """只輸出 corrected_text 非 NULL 且 is_skipped=False 的段落。"""
    db, api_key_id = jsonl_setup
    sess_id = _seed_session(
        db,
        api_key_id=api_key_id,
        segments=[
            {"index": 0, "start": 0.0, "end": 1.0, "original": "a",
             "corrected": "A", "speaker": "S0", "skipped": False},
            {"index": 1, "start": 1.0, "end": 2.0, "original": "b",
             "corrected": None, "speaker": "S0", "skipped": False},   # NULL → 跳過
            {"index": 2, "start": 2.0, "end": 3.0, "original": "c",
             "corrected": "C", "speaker": "S1", "skipped": True},     # skipped → 跳過
        ],
    )
    out = session_to_jsonl(db, sess_id, api_key_id=api_key_id)
    lines = [ln for ln in out.strip().split("\n") if ln]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["text"] == "A"
    assert rec["speaker"] == "S0"
    assert rec["start"] == 0.0
    assert rec["end"] == 1.0


def test_session_to_jsonl_empty_session(jsonl_setup) -> None:
    """空 session（無段落）回傳空字串。"""
    db, api_key_id = jsonl_setup
    sess_id = _seed_session(db, api_key_id=api_key_id, segments=[])
    out = session_to_jsonl(db, sess_id, api_key_id=api_key_id)
    assert out == ""
