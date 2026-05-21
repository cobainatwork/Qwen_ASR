"""Correction export endpoints: export-jsonl / export-excel / evaluate-quality.

Four test cases per CLAUDE.md #27 (happy / reject / wildcard):
  1. export-jsonl → 200 + application/x-ndjson + body contains corrected text
  2. export-excel → 200 + correct MIME + non-empty body
  3. evaluate-quality → 200 + success=True + score field (mocked quality service)
  4. all 3 endpoints → 403 without asr:write scope

Self-contained fixtures following project pattern (test_correction_router.py).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.correction import router as correction_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(correction_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


# ---------------------------------------------------------------------------
# Shared setup fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def exports_setup(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Seed two API keys (asr:write and asr:read-only) + session + segment.

    Returns:
        (client, write_token, read_token, session_id)
    """
    monkeypatch.setenv("API_KEY", "exports-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    hmac_key = derive_hmac_key("exports-test")

    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, "
            "correction_segments, audio_files, datasets, dataset_samples CASCADE"
        )
    )

    # asr:write key
    write_token = "exports-write-token"
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'exports-write', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(write_token), "p": lookup_prefix(write_token, hmac_key)},
    )
    write_key_id = int(db_session.execute(
        text("SELECT id FROM api_keys WHERE name = 'exports-write'")
    ).scalar_one())

    # asr:read-only key (no asr:write)
    read_token = "exports-read-token"
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'exports-read', '{asr:read}')"
        ),
        {"h": hash_token(read_token), "p": lookup_prefix(read_token, hmac_key)},
    )

    # audio_file
    db_session.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size, duration_sec) "
            "VALUES (:a, 'ep.wav', '/tmp/ep.wav', 1024, 5.0)"
        ),
        {"a": write_key_id},
    )
    audio_id = int(db_session.execute(
        text("SELECT id FROM audio_files WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": write_key_id},
    ).scalar_one())

    # transcription
    db_session.execute(
        text(
            "INSERT INTO transcriptions "
            "(api_key_id, source, model_name, model_version, transcript_text, duration_sec) "
            "VALUES (:a, 'upload', 'm', 'v1', 'orig', 5.0)"
        ),
        {"a": write_key_id},
    )
    tx_id = int(db_session.execute(
        text("SELECT id FROM transcriptions WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": write_key_id},
    ).scalar_one())
    db_session.execute(
        text("UPDATE audio_files SET transcription_id = :t WHERE id = :a"),
        {"t": tx_id, "a": audio_id},
    )

    # correction_session
    db_session.execute(
        text(
            "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
            "VALUES (:a, :t, 'ep-sess')"
        ),
        {"a": write_key_id, "t": tx_id},
    )
    session_id = int(db_session.execute(
        text("SELECT id FROM correction_sessions WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": write_key_id},
    ).scalar_one())

    # one corrected segment
    db_session.execute(
        text(
            "INSERT INTO correction_segments "
            "(session_id, segment_index, start_sec, end_sec, "
            "original_text, corrected_text, speaker_label, is_skipped) "
            "VALUES (:s, 0, 0.0, 1.0, 'orig', 'CorrectedA', 'S0', false)"
        ),
        {"s": session_id},
    )
    db_session.commit()

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, write_token, read_token, session_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_export_jsonl_endpoint(exports_setup) -> None:
    """POST export-jsonl → 200 + application/x-ndjson + corrected text in body."""
    client, write_token, _, session_id = exports_setup
    r = client.post(
        f"/api/v1/correction/sessions/{session_id}/export-jsonl",
        headers=_auth(write_token),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert "CorrectedA" in r.content.decode("utf-8")


def test_export_excel_endpoint(exports_setup) -> None:
    """POST export-excel → 200 + xlsx MIME + non-empty body."""
    client, write_token, _, session_id = exports_setup
    r = client.post(
        f"/api/v1/correction/sessions/{session_id}/export-excel",
        headers=_auth(write_token),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert int(r.headers.get("content-length", len(r.content))) > 0
    assert len(r.content) > 0


def test_evaluate_quality_endpoint(exports_setup) -> None:
    """POST evaluate-quality → 200 + success=True + score field (mocked)."""
    client, write_token, _, session_id = exports_setup
    with patch(
        "app.services.correction.quality_evaluator.evaluate_text_quality",
        return_value={"score": 0.9, "issues": []},
    ):
        r = client.post(
            f"/api/v1/correction/sessions/{session_id}/evaluate-quality",
            headers=_auth(write_token),
        )
    assert r.status_code == 200
    payload = r.json()
    assert payload["success"] is True
    assert payload["data"]["score"] == 0.9
    assert payload["data"]["issues"] == []


def test_exports_reject_without_write_scope(exports_setup) -> None:
    """asr:read-only token → 403 for all 3 export endpoints."""
    client, _, read_token, session_id = exports_setup
    for path in ["export-jsonl", "export-excel", "evaluate-quality"]:
        r = client.post(
            f"/api/v1/correction/sessions/{session_id}/{path}",
            headers=_auth(read_token),
        )
        assert r.status_code == 403, f"{path} expected 403, got {r.status_code}"
