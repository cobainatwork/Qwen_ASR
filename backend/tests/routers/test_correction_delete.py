"""DELETE /api/v1/correction/sessions/{session_id} — delete correction session endpoint.

Four test cases per CLAUDE.md #27 (happy / 404-not-found / 404-tenant / 403-scope):
  1. happy: create session with 5 segments → DELETE → 204 + DB row gone + segments CASCADE cleaned
  2. not_found: DELETE non-existent session_id → 404 CORRECTION_SESSION_NOT_FOUND
  3. tenant_isolation: DELETE session belonging to other tenant → 404
  4. scope_reject: token with asr:read only → 403
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


def _insert_transcription(db: Session, api_key_id: int) -> int:
    db.execute(
        text(
            "INSERT INTO transcriptions "
            "(api_key_id, source, model_name, model_version, transcript_text, "
            "duration_sec, file_name, status) "
            "VALUES (:a, 'upload', 'm', 'v1', 'test', 10.0, 'test.wav', 'completed')"
        ),
        {"a": api_key_id},
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


def _insert_session_with_segments(
    db: Session, api_key_id: int, tx_id: int, segment_count: int = 5
) -> int:
    """Insert a correction_session + N segments directly via SQL. Returns session_id."""
    db.execute(
        text(
            "INSERT INTO correction_sessions (api_key_id, transcription_id, name, status) "
            "VALUES (:a, :t, 'Delete Test Session', 'in_progress')"
        ),
        {"a": api_key_id, "t": tx_id},
    )
    session_id = int(
        db.execute(
            text(
                "SELECT id FROM correction_sessions WHERE api_key_id = :a "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id},
        ).scalar_one()
    )
    for i in range(segment_count):
        db.execute(
            text(
                "INSERT INTO correction_segments "
                "(session_id, segment_index, start_sec, end_sec, original_text) "
                "VALUES (:sid, :idx, :s, :e, :txt)"
            ),
            {
                "sid": session_id,
                "idx": i,
                "s": float(i * 10),
                "e": float((i + 1) * 10),
                "txt": f"段落 {i + 1}",
            },
        )
    db.flush()
    return session_id


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def base_setup(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Truncate tables + set env vars. Returns (client, hmac_key, api_key_id, write_token)."""
    monkeypatch.setenv("API_KEY", "delete-sess-test")
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

    hmac_key = derive_hmac_key("delete-sess-test")
    write_token = "delete-write-token"
    api_key_id = _insert_api_key(
        db_session, hmac_key, write_token, "delete-write", "{asr:write}"
    )

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, hmac_key, api_key_id, write_token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_session_happy(base_setup, db_session: Session) -> None:
    """Create session + 5 segments → DELETE → 204 + row gone + segments CASCADE cleaned."""
    client, _, api_key_id, write_token = base_setup

    tx_id = _insert_transcription(db_session, api_key_id)
    session_id = _insert_session_with_segments(db_session, api_key_id, tx_id, segment_count=5)

    # Verify segments exist before delete
    seg_count_before = db_session.execute(
        text("SELECT COUNT(*) FROM correction_segments WHERE session_id = :sid"),
        {"sid": session_id},
    ).scalar_one()
    assert seg_count_before == 5

    r = client.delete(
        f"/api/v1/correction/sessions/{session_id}",
        headers=_auth(write_token),
    )
    assert r.status_code == 204
    assert r.content == b""

    # Session row must be gone
    sess_row = db_session.execute(
        text("SELECT id FROM correction_sessions WHERE id = :sid"),
        {"sid": session_id},
    ).scalar_one_or_none()
    assert sess_row is None

    # Segments must be CASCADE deleted
    seg_count_after = db_session.execute(
        text("SELECT COUNT(*) FROM correction_segments WHERE session_id = :sid"),
        {"sid": session_id},
    ).scalar_one()
    assert seg_count_after == 0


def test_delete_session_not_found(base_setup) -> None:
    """DELETE non-existent session_id → 404 CORRECTION_SESSION_NOT_FOUND."""
    client, _, _, write_token = base_setup

    r = client.delete(
        "/api/v1/correction/sessions/99999",
        headers=_auth(write_token),
    )
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "CORRECTION_SESSION_NOT_FOUND"


def test_delete_session_tenant_isolation(base_setup, db_session: Session) -> None:
    """Session belonging to another tenant → 404 (treated as not found)."""
    client, hmac_key, _, write_token = base_setup

    # Create second tenant + session
    other_token = "delete-other-write-token"
    other_key_id = _insert_api_key(
        db_session, hmac_key, other_token, "delete-other-write", "{asr:write}"
    )
    other_tx_id = _insert_transcription(db_session, other_key_id)
    other_session_id = _insert_session_with_segments(
        db_session, other_key_id, other_tx_id, segment_count=2
    )

    # Primary tenant tries to delete other tenant's session
    r = client.delete(
        f"/api/v1/correction/sessions/{other_session_id}",
        headers=_auth(write_token),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CORRECTION_SESSION_NOT_FOUND"

    # Other tenant's session must still exist
    still_exists = db_session.execute(
        text("SELECT id FROM correction_sessions WHERE id = :sid"),
        {"sid": other_session_id},
    ).scalar_one_or_none()
    assert still_exists is not None


def test_delete_session_scope_reject(base_setup, db_session: Session) -> None:
    """Token with asr:read only → 403."""
    client, hmac_key, _, _ = base_setup
    read_token = "delete-read-only-token"
    _insert_api_key(
        db_session, hmac_key, read_token, "delete-read-only", "{asr:read}"
    )
    db_session.flush()

    r = client.delete(
        "/api/v1/correction/sessions/1",
        headers=_auth(read_token),
    )
    assert r.status_code == 403
