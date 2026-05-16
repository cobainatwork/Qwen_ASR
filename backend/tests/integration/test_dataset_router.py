from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.dataset import router as dataset_router

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(dataset_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def dataset_app(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "dataset-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPPORTED_AUDIO_FORMATS", "wav,mp3")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ds-token-xyz"
    hmac_key = derive_hmac_key("dataset-test")
    db_session.execute(text("TRUNCATE api_keys, datasets, dataset_samples, audio_files CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'dsk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    return _build_app(db_session), raw_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_dataset(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset",
            json={"name": "ds1", "description": "test"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["sample_count"] == 0
    assert body["data"]["total_duration_sec"] == 0.0


def test_upload_sample_pipeline(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token))
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "你好世界"},
                headers=_headers(token),
            )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["transcript"] == "你好世界"
    assert body["data"]["duration_sec"] > 0


def test_upload_sample_dataset_not_found(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/dataset/9999/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "test"},
                headers=_headers(token),
            )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DATASET_NOT_FOUND"


def test_upload_sample_empty_transcript(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token))
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "   "},
                headers=_headers(token),
            )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DATASET_SAMPLE_INVALID"


def test_upload_sample_rejects_zip_disguised(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token))
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "fake_extension.wav.zip").open("rb") as f:
            resp = client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "test"},
                headers=_headers(token),
            )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "AUDIO_MIME_INVALID"


def test_list_samples(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token))
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"transcript": "句子 1"},
                headers=_headers(token),
            )
        resp = client.get(f"/api/v1/dataset/{dataset_id}/samples", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
