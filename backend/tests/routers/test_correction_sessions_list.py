"""GET /api/v1/correction/sessions — list endpoint.

Five test cases per CLAUDE.md #27 (happy / pagination / empty / reject / tenant):
  1. happy: 3 sessions seeded → items.length=3, pagination.total=3
  2. pagination: 5 sessions, limit=2, page=2 → items.length=2, page=2
  3. empty: 0 sessions → items=[], total=0
  4. scope reject: dataset:read only → 403
  5. tenant isolation: other tenant's sessions are invisible
"""
from __future__ import annotations

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
            "(api_key_id, source, model_name, model_version, transcript_text, duration_sec) "
            "VALUES (:a, 'upload', 'm', 'v1', 'txt', 5.0)"
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


def _insert_session(
    db: Session, api_key_id: int, tx_id: int, name: str
) -> int:
    db.execute(
        text(
            "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
            "VALUES (:a, :t, :n)"
        ),
        {"a": api_key_id, "t": tx_id, "n": name},
    )
    return int(
        db.execute(
            text(
                "SELECT id FROM correction_sessions WHERE api_key_id = :a "
                "AND name = :n ORDER BY id DESC LIMIT 1"
            ),
            {"a": api_key_id, "n": name},
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def base_setup(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Truncate tables + set env vars. Returns (client, hmac_key, api_key_id, read_token)."""
    monkeypatch.setenv("API_KEY", "list-test")
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

    hmac_key = derive_hmac_key("list-test")
    read_token = "list-read-token"
    api_key_id = _insert_api_key(
        db_session, hmac_key, read_token, "list-read", "{asr:read}"
    )

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, hmac_key, api_key_id, read_token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_sessions_happy(base_setup, db_session: Session) -> None:
    """3 sessions seeded → items.length=3, pagination.total=3."""
    client, _, api_key_id, read_token = base_setup
    for i in range(3):
        tx_id = _insert_transcription(db_session, api_key_id)
        _insert_session(db_session, api_key_id, tx_id, f"sess-{i}")
    db_session.flush()

    r = client.get("/api/v1/correction/sessions", headers=_auth(read_token))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["data"]["items"]) == 3
    assert body["data"]["pagination"]["total"] == 3
    assert body["data"]["pagination"]["page"] == 1


def test_list_sessions_pagination(base_setup, db_session: Session) -> None:
    """5 sessions, limit=2, page=2 → items.length=2, page=2."""
    client, _, api_key_id, read_token = base_setup
    for i in range(5):
        tx_id = _insert_transcription(db_session, api_key_id)
        _insert_session(db_session, api_key_id, tx_id, f"pg-sess-{i}")
    db_session.flush()

    r = client.get(
        "/api/v1/correction/sessions?page=2&limit=2",
        headers=_auth(read_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["data"]["items"]) == 2
    assert body["data"]["pagination"]["page"] == 2
    assert body["data"]["pagination"]["total"] == 5
    assert body["data"]["pagination"]["total_pages"] == 3


def test_list_sessions_empty(base_setup) -> None:
    """0 sessions → items=[], total=0."""
    client, _, _, read_token = base_setup

    r = client.get("/api/v1/correction/sessions", headers=_auth(read_token))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["data"]["pagination"]["total"] == 0


def test_list_sessions_scope_reject(base_setup, db_session: Session) -> None:
    """dataset:read scope only → 403."""
    client, hmac_key, _, _ = base_setup
    bad_token = "list-bad-scope-token"
    _insert_api_key(
        db_session, hmac_key, bad_token, "list-bad-scope", "{dataset:read}"
    )
    db_session.flush()

    r = client.get("/api/v1/correction/sessions", headers=_auth(bad_token))
    assert r.status_code == 403


def test_list_sessions_tenant_isolation(
    base_setup, db_session: Session
) -> None:
    """Other tenant's sessions are invisible."""
    client, hmac_key, api_key_id, read_token = base_setup

    # Seed a session for the primary tenant
    tx_id = _insert_transcription(db_session, api_key_id)
    _insert_session(db_session, api_key_id, tx_id, "primary-sess")

    # Seed another tenant with its own session
    other_token = "list-other-token"
    other_key_id = _insert_api_key(
        db_session, hmac_key, other_token, "list-other", "{asr:read}"
    )
    other_tx_id = _insert_transcription(db_session, other_key_id)
    _insert_session(db_session, other_key_id, other_tx_id, "other-sess")
    db_session.flush()

    r = client.get("/api/v1/correction/sessions", headers=_auth(read_token))
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["pagination"]["total"] == 1
    assert body["data"]["items"][0]["name"] == "primary-sess"
