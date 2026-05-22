"""DELETE /api/v1/asr/transcriptions/{transcription_id} — delete transcription endpoint.

Five test cases per CLAUDE.md #27 (happy / 404-not-found / 404-tenant / 403-scope /
audio_file-preserved):
  1. happy: transcription + correction_session + 5 segments → DELETE → 204 + all CASCADE deleted
  2. not_found: DELETE non-existent transcription_id → 404 TRANSCRIPTION_NOT_FOUND
  3. tenant_isolation: DELETE transcription belonging to other tenant → 404
  4. scope_reject: token with asr:read only → 403
  5. audio_file_preserved: DELETE transcription → audio_file row still exists in DB
"""
from __future__ import annotations

import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.asr import router as asr_router
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
    app.include_router(asr_router)
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


def _insert_audio_file(db: Session, api_key_id: int, transcription_id: int | None = None) -> int:
    db.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, storage_path, original_name, mime_type, "
            "file_size, sha256, transcription_id) "
            "VALUES (:a, 'uploads/dummy.wav', 'dummy.wav', 'audio/wav', 1024, 'abc123', :tx)"
        ),
        {"a": api_key_id, "tx": transcription_id},
    )
    return int(
        db.execute(
            text(
                "SELECT id FROM audio_files WHERE api_key_id = :a "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id},
        ).scalar_one()
    )


def _insert_transcription(db: Session, api_key_id: int, audio_file_id: int | None = None) -> int:
    db.execute(
        text(
            "INSERT INTO transcriptions "
            "(api_key_id, audio_file_id, source, model_name, model_version, "
            "transcript_text, duration_sec, file_name, status) "
            "VALUES (:a, :af, 'upload', 'm', 'v1', 'test', 10.0, 'test.wav', 'completed')"
        ),
        {"a": api_key_id, "af": audio_file_id},
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


def _insert_correction_session_with_segments(
    db: Session, api_key_id: int, tx_id: int, segment_count: int = 5
) -> int:
    """Insert a correction_session + N segments. Returns session_id."""
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
    monkeypatch.setenv("API_KEY", "delete-tx-test")
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

    hmac_key = derive_hmac_key("delete-tx-test")
    write_token = "delete-tx-write-token"
    api_key_id = _insert_api_key(
        db_session, hmac_key, write_token, "delete-tx-write", "{asr:write}"
    )

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, hmac_key, api_key_id, write_token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_transcription_happy(base_setup, db_session: Session) -> None:
    """Transcription + correction_session + 5 segments → DELETE → 204 + all CASCADE deleted."""
    client, _, api_key_id, write_token = base_setup

    tx_id = _insert_transcription(db_session, api_key_id)
    session_id = _insert_correction_session_with_segments(
        db_session, api_key_id, tx_id, segment_count=5
    )

    # Verify segments exist before delete
    seg_count_before = db_session.execute(
        text("SELECT COUNT(*) FROM correction_segments WHERE session_id = :sid"),
        {"sid": session_id},
    ).scalar_one()
    assert seg_count_before == 5

    r = client.delete(
        f"/api/v1/asr/transcriptions/{tx_id}",
        headers=_auth(write_token),
    )
    assert r.status_code == 204
    assert r.content == b""

    # Transcription row must be gone
    tx_row = db_session.execute(
        text("SELECT id FROM transcriptions WHERE id = :tid"),
        {"tid": tx_id},
    ).scalar_one_or_none()
    assert tx_row is None

    # Correction session must be CASCADE deleted
    sess_row = db_session.execute(
        text("SELECT id FROM correction_sessions WHERE id = :sid"),
        {"sid": session_id},
    ).scalar_one_or_none()
    assert sess_row is None

    # Segments must be CASCADE deleted (via session CASCADE)
    seg_count_after = db_session.execute(
        text("SELECT COUNT(*) FROM correction_segments WHERE session_id = :sid"),
        {"sid": session_id},
    ).scalar_one()
    assert seg_count_after == 0


def test_delete_transcription_not_found(base_setup) -> None:
    """DELETE non-existent transcription_id → 404 TRANSCRIPTION_NOT_FOUND."""
    client, _, _, write_token = base_setup

    r = client.delete(
        "/api/v1/asr/transcriptions/99999",
        headers=_auth(write_token),
    )
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "TRANSCRIPTION_NOT_FOUND"


def test_delete_transcription_tenant_isolation(base_setup, db_session: Session) -> None:
    """Transcription belonging to another tenant → 404 (treated as not found)."""
    client, hmac_key, _, write_token = base_setup

    # Create second tenant + transcription
    other_token = "delete-tx-other-write-token"
    other_key_id = _insert_api_key(
        db_session, hmac_key, other_token, "delete-tx-other-write", "{asr:write}"
    )
    other_tx_id = _insert_transcription(db_session, other_key_id)
    db_session.flush()

    # Primary tenant tries to delete other tenant's transcription
    r = client.delete(
        f"/api/v1/asr/transcriptions/{other_tx_id}",
        headers=_auth(write_token),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TRANSCRIPTION_NOT_FOUND"

    # Other tenant's transcription must still exist
    still_exists = db_session.execute(
        text("SELECT id FROM transcriptions WHERE id = :tid"),
        {"tid": other_tx_id},
    ).scalar_one_or_none()
    assert still_exists is not None


def test_delete_transcription_scope_reject(base_setup, db_session: Session) -> None:
    """Token with asr:read only → 403."""
    client, hmac_key, _, _ = base_setup
    read_token = "delete-tx-read-only-token"
    _insert_api_key(
        db_session, hmac_key, read_token, "delete-tx-read-only", "{asr:read}"
    )
    db_session.flush()

    r = client.delete(
        "/api/v1/asr/transcriptions/1",
        headers=_auth(read_token),
    )
    assert r.status_code == 403


def test_delete_transcription_audio_file_preserved(base_setup, db_session: Session) -> None:
    """DELETE transcription → audio_file row still exists; transcription_id SET NULL."""
    client, _, api_key_id, write_token = base_setup

    # Insert audio_file without transcription_id first, then insert transcription,
    # then back-link audio_file.transcription_id to exercise the ON DELETE SET NULL path.
    audio_file_id = _insert_audio_file(db_session, api_key_id, transcription_id=None)
    tx_id = _insert_transcription(db_session, api_key_id, audio_file_id=audio_file_id)
    # Link audio_file → transcription (this is the FK that was missing SET NULL)
    db_session.execute(
        text("UPDATE audio_files SET transcription_id = :tx WHERE id = :af"),
        {"tx": tx_id, "af": audio_file_id},
    )
    db_session.flush()

    # Confirm link is in place before delete
    tx_id_before = db_session.execute(
        text("SELECT transcription_id FROM audio_files WHERE id = :af"),
        {"af": audio_file_id},
    ).scalar_one_or_none()
    assert tx_id_before == tx_id

    r = client.delete(
        f"/api/v1/asr/transcriptions/{tx_id}",
        headers=_auth(write_token),
    )
    assert r.status_code == 204

    # audio_file row must still exist (not cascade-deleted)
    af_row = db_session.execute(
        text("SELECT id, transcription_id FROM audio_files WHERE id = :af_id"),
        {"af_id": audio_file_id},
    ).scalar_one_or_none()
    assert af_row is not None

    # transcription_id must be NULL (ON DELETE SET NULL applied)
    tx_id_after = db_session.execute(
        text("SELECT transcription_id FROM audio_files WHERE id = :af"),
        {"af": audio_file_id},
    ).scalar_one_or_none()
    assert tx_id_after is None
