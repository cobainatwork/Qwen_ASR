"""Audio stream endpoint: GET /api/v1/audio/{audio_file_id}/stream.

Six test cases per CLAUDE.md #27 (happy / reject / wildcard):
  1. Full content → 200 + Accept-Ranges
  2. Range request → 206 + Content-Range
  3. Out-of-bounds range → 416
  4. Cross-tenant → 404
  5. Missing asr:read scope → 403
  6. Admin wildcard scope → pass (200 or 206)

Fixtures are self-contained, following the project's established pattern
(see test_correction_router.py, test_asr_transcribe.py).
AudioFile model fields: file_size (not size_bytes), original_sample_rate (not sample_rate).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.audio import router as audio_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Shared WAV bytes (minimal valid RIFF header + 2 s of silence @ 16kHz)
# ---------------------------------------------------------------------------
_WAV_BYTES = b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 32000  # ~2 kB


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(audio_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


def _insert_api_key(
    db_session: Session,
    *,
    raw_token: str,
    hmac_key: bytes,
    name: str,
    scopes: str,
) -> int:
    """Insert an api_key row and return its id."""
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, :n, :s)"
        ),
        {
            "h": hash_token(raw_token),
            "p": lookup_prefix(raw_token, hmac_key),
            "n": name,
            "s": scopes,
        },
    )
    row = db_session.execute(
        text("SELECT id FROM api_keys WHERE name = :n"), {"n": name}
    ).first()
    assert row is not None
    return int(row[0])


def _insert_audio_file(
    db_session: Session,
    *,
    api_key_id: int,
    wav_path: str,
    size: int,
) -> int:
    """Insert an audio_files row and return its id."""
    db_session.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size, mime_type, duration_sec) "
            "VALUES (:a, 'test.wav', :p, :s, 'audio/wav', 1.0)"
        ),
        {"a": api_key_id, "p": wav_path, "s": size},
    )
    row = db_session.execute(
        text("SELECT id FROM audio_files WHERE api_key_id = :a ORDER BY id DESC LIMIT 1"),
        {"a": api_key_id},
    ).first()
    assert row is not None
    return int(row[0])


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audio_setup(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Primary tenant: asr:read token + on-disk WAV + DB row.

    Returns (client, audio_file_id, raw_token).
    """
    monkeypatch.setenv("API_KEY", "audio-stream-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    hmac_key = derive_hmac_key("audio-stream-test")
    raw_token = "audio-test-token-read"

    db_session.execute(
        text("TRUNCATE api_keys, audio_files CASCADE")
    )

    api_key_id = _insert_api_key(
        db_session,
        raw_token=raw_token,
        hmac_key=hmac_key,
        name="audio-read-key",
        scopes="{asr:read}",
    )

    wav_path = tmp_path / "test.wav"
    wav_path.write_bytes(_WAV_BYTES)

    audio_file_id = _insert_audio_file(
        db_session,
        api_key_id=api_key_id,
        wav_path=str(wav_path),
        size=len(_WAV_BYTES),
    )
    db_session.commit()

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, audio_file_id, raw_token


@pytest.fixture
def audio_setup_admin(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Admin wildcard tenant: admin scope token + on-disk WAV + DB row.

    Returns (client, audio_file_id, raw_token).
    """
    monkeypatch.setenv("API_KEY", "audio-stream-admin")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    hmac_key = derive_hmac_key("audio-stream-admin")
    raw_token = "audio-admin-token-xyz"

    db_session.execute(
        text("TRUNCATE api_keys, audio_files CASCADE")
    )

    api_key_id = _insert_api_key(
        db_session,
        raw_token=raw_token,
        hmac_key=hmac_key,
        name="audio-admin-key",
        scopes="{admin}",
    )

    wav_path = tmp_path / "admin_test.wav"
    wav_path.write_bytes(_WAV_BYTES)

    audio_file_id = _insert_audio_file(
        db_session,
        api_key_id=api_key_id,
        wav_path=str(wav_path),
        size=len(_WAV_BYTES),
    )
    db_session.commit()

    app = _build_app(db_session)
    with TestClient(app) as client:
        yield client, audio_file_id, raw_token


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_stream_full_audio_returns_200(audio_setup) -> None:
    """Full content request: 200 + Accept-Ranges + Content-Length."""
    client, audio_file_id, raw_token = audio_setup
    r = client.get(
        f"/api/v1/audio/{audio_file_id}/stream",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.headers["accept-ranges"] == "bytes"
    assert int(r.headers["content-length"]) == len(_WAV_BYTES)


def test_stream_with_range_returns_206(audio_setup) -> None:
    """Range request bytes=0-1023: 206 + Content-Range + 1024-byte body."""
    client, audio_file_id, raw_token = audio_setup
    r = client.get(
        f"/api/v1/audio/{audio_file_id}/stream",
        headers={
            "Authorization": f"Bearer {raw_token}",
            "Range": "bytes=0-1023",
        },
    )
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-1023/")
    assert int(r.headers["content-length"]) == 1024
    assert len(r.content) == 1024


def test_stream_range_out_of_bounds_returns_416(audio_setup) -> None:
    """Out-of-bounds range: 416 + Content-Range: bytes */<size>."""
    client, audio_file_id, raw_token = audio_setup
    r = client.get(
        f"/api/v1/audio/{audio_file_id}/stream",
        headers={
            "Authorization": f"Bearer {raw_token}",
            "Range": "bytes=999999999-",
        },
    )
    assert r.status_code == 416
    assert f"bytes */{len(_WAV_BYTES)}" in r.headers.get("content-range", "")


def test_stream_cross_tenant_returns_404(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    audio_setup,
) -> None:
    """Cross-tenant access: AudioFileRepository returns None → 404."""
    # audio_setup owns the audio file under primary tenant
    _, audio_file_id, _ = audio_setup

    # Create a second tenant key in the same db_session
    monkeypatch.setenv("API_KEY", "audio-stream-test")
    from app.core.config import get_settings
    get_settings.cache_clear()

    hmac_key = derive_hmac_key("audio-stream-test")
    raw_other = "audio-other-tenant-token"

    # Insert second key (TRUNCATE already ran in audio_setup, so just insert)
    _insert_api_key(
        db_session,
        raw_token=raw_other,
        hmac_key=hmac_key,
        name="audio-other-key",
        scopes="{asr:read}",
    )
    db_session.commit()

    client, _, _ = audio_setup
    r = client.get(
        f"/api/v1/audio/{audio_file_id}/stream",
        headers={"Authorization": f"Bearer {raw_other}"},
    )
    assert r.status_code == 404


def test_stream_without_scope_returns_403(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    audio_setup,
) -> None:
    """Token with dataset:read only (no asr:read): 403."""
    monkeypatch.setenv("API_KEY", "audio-stream-test")
    from app.core.config import get_settings
    get_settings.cache_clear()

    hmac_key = derive_hmac_key("audio-stream-test")
    raw_noscope = "audio-noscope-token"

    _insert_api_key(
        db_session,
        raw_token=raw_noscope,
        hmac_key=hmac_key,
        name="audio-noscope-key",
        scopes="{dataset:read}",
    )
    db_session.commit()

    client, audio_file_id, _ = audio_setup
    r = client.get(
        f"/api/v1/audio/{audio_file_id}/stream",
        headers={"Authorization": f"Bearer {raw_noscope}"},
    )
    assert r.status_code == 403


def test_stream_admin_wildcard_passes(audio_setup_admin) -> None:
    """Admin wildcard scope: should pass scope check (200 or 206)."""
    client, audio_file_id, raw_token = audio_setup_admin
    r = client.get(
        f"/api/v1/audio/{audio_file_id}/stream",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert r.status_code in (200, 206)
