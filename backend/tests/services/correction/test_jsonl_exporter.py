"""JSONL 匯出：排除 is_skipped 與 corrected_text=NULL 的段落。

Self-contained fixture — follows project pattern (test_correction_router.py).
"""
from __future__ import annotations

import json

import pytest
from app.services.correction.jsonl_exporter import session_to_jsonl
from sqlalchemy.orm import Session
from tests.services.correction.conftest import seed_session

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def jsonl_setup(db_session: Session, correction_service_setup):
    """回傳 (db_session, api_key_id)，TRUNCATE 確保乾淨環境。"""
    return correction_service_setup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_session_to_jsonl_includes_only_corrected(jsonl_setup) -> None:
    """只輸出 corrected_text 非 NULL 且 is_skipped=False 的段落。"""
    db, api_key_id = jsonl_setup
    sess_id = seed_session(
        db,
        api_key_id=api_key_id,
        audio_filename="jsonl.wav",
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
    sess_id = seed_session(db, api_key_id=api_key_id, audio_filename="jsonl-empty.wav", segments=[])
    out = session_to_jsonl(db, sess_id, api_key_id=api_key_id)
    assert out == ""
