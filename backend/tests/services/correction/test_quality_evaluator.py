"""Quality evaluator：對接 dataset quality service（mock contract test）。

Self-contained fixture — follows project pattern (test_correction_router.py).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from app.services.correction.quality_evaluator import evaluate_session_quality
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
    db.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size, duration_sec) "
            "VALUES (:a, 'qual.wav', '/tmp/qual.wav', 1024, 5.0)"
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
            "VALUES (:a, :t, 'qual-test')"
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
def qual_setup(db_session: Session):
    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, "
            "correction_segments, audio_files CASCADE"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES ('$argon2id$dummy', '1234567890abcdef', 'qual-key', '{asr:write}')"
        )
    )
    api_key_id = int(db_session.execute(
        text("SELECT id FROM api_keys WHERE name = 'qual-key'")
    ).scalar_one())
    db_session.commit()
    return db_session, api_key_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evaluate_calls_dataset_quality_service(qual_setup) -> None:
    """evaluate_session_quality 應將校正文字清單傳入 evaluate_text_quality 並回傳其結果。"""
    db, api_key_id = qual_setup
    sess_id = _seed_session(
        db,
        api_key_id=api_key_id,
        segments=[
            {"index": 0, "start": 0.0, "end": 1.0, "original": "a",
             "corrected": "A", "speaker": "S0", "skipped": False},
        ],
    )
    with patch("app.services.correction.quality_evaluator.evaluate_text_quality") as mock_fn:
        mock_fn.return_value = {"score": 0.95, "issues": []}
        result = evaluate_session_quality(db, sess_id, api_key_id=api_key_id)

    assert result["score"] == 0.95
    mock_fn.assert_called_once()
    # 校正文字「A」必須出現在傳入的 texts 清單中
    call_args = mock_fn.call_args[0]
    assert len(call_args) == 1
    assert "A" in call_args[0]
