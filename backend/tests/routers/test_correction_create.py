"""POST /api/v1/correction/sessions — create correction session endpoint.

Six test cases per CLAUDE.md #27 (happy / idempotent / no-speakers / not-found / tenant / scope):
  1. happy: transcription with speaker turns + word timestamps → session + N segments
  2. idempotent: second POST same transcription_id → returns same session_id
  3. no_speakers: transcription has transcript_text but no speakers → 1 segment
  4. transcription_not_found: unknown transcription_id → 404 TRANSCRIPTION_NOT_FOUND
  5. tenant_isolation: transcription belongs to other tenant → 404
  6. scope_reject: token has asr:read only → 403
"""
from __future__ import annotations

import json

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
# Helpers
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _insert_api_key(
    db: Session,
    hmac_key: bytes,
    token: str,
    name: str,
    scopes: str,
) -> int:
    db.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, :n, :s)"
        ),
        {
            "h": hash_token(token),
            "p": lookup_prefix(token, hmac_key),
            "n": name,
            "s": scopes,
        },
    )
    return int(
        db.execute(
            text("SELECT id FROM api_keys WHERE name = :n"), {"n": name}
        ).scalar_one()
    )


def _insert_transcription(
    db: Session,
    api_key_id: int,
    *,
    transcript_text: str = "hello world",
    speakers: list | None = None,
    timestamps: list | None = None,
    file_name: str | None = "test.wav",
    duration_sec: float = 10.0,
) -> int:
    db.execute(
        text(
            "INSERT INTO transcriptions "
            "(api_key_id, source, model_name, model_version, transcript_text, "
            "duration_sec, file_name, speakers, timestamps, status) "
            "VALUES (:a, 'upload', 'm', 'v1', :txt, :dur, :fn, "
            ":sp::jsonb, :ts::jsonb, 'completed')"
        ),
        {
            "a": api_key_id,
            "txt": transcript_text,
            "dur": duration_sec,
            "fn": file_name,
            "sp": json.dumps(speakers) if speakers is not None else None,
            "ts": json.dumps(timestamps) if timestamps is not None else None,
        },
    )
    return int(
        db.execute(
            text(
                "SELECT id FROM transcriptions WHERE api_key_id = :a "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id},
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def base_setup(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Truncate tables + set env vars. Returns (client, hmac_key, api_key_id, write_token)."""
    monkeypatch.setenv("API_KEY", "create-sess-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, "
            "correction_segments, audio_files, datasets, dataset_samples CASCADE"
        )
    )

    hmac_key = derive_hmac_key("create-sess-test")
    write_token = "create-write-token"
    api_key_id = _insert_api_key(
        db_session, hmac_key, write_token, "create-write", "{asr:write}"
    )

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, hmac_key, api_key_id, write_token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_session_happy_with_speakers(base_setup, db_session: Session) -> None:
    """Transcription with 2 speaker turns + word timestamps → session + 2 segments."""
    client, _, api_key_id, write_token = base_setup

    speakers = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 5.0},
        {"speaker": "SPEAKER_01", "start": 5.0, "end": 10.0},
    ]
    timestamps = [
        {"text": "你好", "start": 0.5, "end": 1.0},
        {"text": "世界", "start": 1.5, "end": 2.0},
        {"text": "再見", "start": 5.5, "end": 6.0},
    ]
    tx_id = _insert_transcription(
        db_session,
        api_key_id,
        transcript_text="你好世界再見",
        speakers=speakers,
        timestamps=timestamps,
    )
    db_session.flush()

    r = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": tx_id},
        headers=_auth(write_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    sess = body["data"]
    assert sess["transcription_id"] == tx_id
    assert sess["status"] == "in_progress"

    # Verify 2 segments were created
    seg_r = client.get(
        f"/api/v1/correction/sessions/{sess['id']}/segments",
        headers=_auth(write_token),
    )
    assert seg_r.status_code == 200
    segs = seg_r.json()["data"]
    assert len(segs) == 2
    assert segs[0]["speaker_label"] == "SPEAKER_00"
    assert segs[1]["speaker_label"] == "SPEAKER_01"
    assert "你好" in segs[0]["original_text"]


def test_create_session_idempotent(base_setup, db_session: Session) -> None:
    """Second POST with same transcription_id returns the same session_id."""
    client, _, api_key_id, write_token = base_setup
    tx_id = _insert_transcription(db_session, api_key_id)
    db_session.flush()

    r1 = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": tx_id},
        headers=_auth(write_token),
    )
    assert r1.status_code == 200
    sess_id_first = r1.json()["data"]["id"]

    r2 = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": tx_id},
        headers=_auth(write_token),
    )
    assert r2.status_code == 200
    sess_id_second = r2.json()["data"]["id"]

    assert sess_id_first == sess_id_second


def test_create_session_no_speakers_one_segment(base_setup, db_session: Session) -> None:
    """Transcription with no speakers → 1 segment containing full transcript_text."""
    client, _, api_key_id, write_token = base_setup
    tx_id = _insert_transcription(
        db_session,
        api_key_id,
        transcript_text="整段逐字稿",
        speakers=None,
        timestamps=None,
        duration_sec=20.0,
    )
    db_session.flush()

    r = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": tx_id},
        headers=_auth(write_token),
    )
    assert r.status_code == 200
    sess_id = r.json()["data"]["id"]

    seg_r = client.get(
        f"/api/v1/correction/sessions/{sess_id}/segments",
        headers=_auth(write_token),
    )
    segs = seg_r.json()["data"]
    assert len(segs) == 1
    assert segs[0]["original_text"] == "整段逐字稿"
    assert segs[0]["end_sec"] == 20.0


def test_create_session_transcription_not_found(base_setup) -> None:
    """Non-existent transcription_id → 404 with TRANSCRIPTION_NOT_FOUND."""
    client, _, _, write_token = base_setup

    r = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": 99999},
        headers=_auth(write_token),
    )
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "TRANSCRIPTION_NOT_FOUND"


def test_create_session_tenant_isolation(base_setup, db_session: Session) -> None:
    """Transcription belonging to another tenant → 404 (treated as not found)."""
    client, hmac_key, _, write_token = base_setup

    # Create a second tenant and seed a transcription under it
    other_token = "create-other-write-token"
    other_key_id = _insert_api_key(
        db_session, hmac_key, other_token, "create-other-write", "{asr:write}"
    )
    other_tx_id = _insert_transcription(db_session, other_key_id)
    db_session.flush()

    # Primary tenant tries to create a session for the other tenant's transcription
    r = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": other_tx_id},
        headers=_auth(write_token),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TRANSCRIPTION_NOT_FOUND"


def test_create_session_scope_reject(base_setup, db_session: Session) -> None:
    """Token with asr:read only → 403."""
    client, hmac_key, _, _ = base_setup
    read_token = "create-read-only-token"
    _insert_api_key(
        db_session, hmac_key, read_token, "create-read-only", "{asr:read}"
    )
    db_session.flush()

    r = client.post(
        "/api/v1/correction/sessions",
        json={"transcription_id": 1},
        headers=_auth(read_token),
    )
    assert r.status_code == 403
