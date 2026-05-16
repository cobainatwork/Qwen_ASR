import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.youtube import router as youtube_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(youtube_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def youtube_app(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "yt-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    # 不執行真實 yt-dlp（背景 task 會失敗，但建立 record 即可）
    monkeypatch.setattr("app.routers.youtube._execute_download", lambda *a, **kw: None)

    raw_token = "yt-token"
    hmac_key = derive_hmac_key("yt-test")
    db_session.execute(text("TRUNCATE api_keys, youtube_downloads CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'ytk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    return _build_app(db_session), raw_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_download_valid_url_creates_record(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "pending"


def test_download_invalid_url(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "https://vimeo.com/123"},
            headers=_headers(token),
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "YOUTUBE_URL_INVALID"


def test_download_non_https(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "http://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=_headers(token),
        )
    assert resp.status_code == 400


def test_list_downloads(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "https://youtu.be/dQw4w9WgXcQ"},
            headers=_headers(token),
        )
        resp = client.get("/api/v1/dataset/youtube/downloads", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
