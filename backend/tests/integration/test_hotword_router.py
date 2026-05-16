import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.hotword import router as hotword_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(hotword_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def hotword_app(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "hotword-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "hw-token-abc"
    hmac_key = derive_hmac_key("hotword-test")
    db_session.execute(text("TRUNCATE api_keys, hotword_groups, hotwords CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'hwk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    return _build_app(db_session), raw_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_group_returns_201(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "客戶名單", "description": "VIP"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "客戶名單"
    assert body["data"]["word_count"] == 0


def test_list_groups_returns_envelope(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        client.post("/api/v1/hotword/groups", json={"name": "g1"}, headers=_headers(token))
        client.post("/api/v1/hotword/groups", json={"name": "g2"}, headers=_headers(token))
        resp = client.get("/api/v1/hotword/groups", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


def test_get_group_not_found(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/hotword/groups/9999", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "HOTWORD_GROUP_NOT_FOUND"


def test_update_group(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/hotword/groups", json={"name": "old-name"}, headers=_headers(token))
        group_id = create_resp.json()["data"]["id"]
        resp = client.put(
            f"/api/v1/hotword/groups/{group_id}",
            json={"name": "new-name"},
            headers=_headers(token),
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "new-name"


def test_delete_group(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/hotword/groups", json={"name": "to-delete"}, headers=_headers(token))
        group_id = create_resp.json()["data"]["id"]
        resp = client.delete(f"/api/v1/hotword/groups/{group_id}", headers=_headers(token))
        get_resp = client.get(f"/api/v1/hotword/groups/{group_id}", headers=_headers(token))
    assert resp.status_code == 200
    assert get_resp.status_code == 404


def test_bulk_upload_shallow_fusion(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/hotword/groups", json={"name": "vip"}, headers=_headers(token))
        group_id = create_resp.json()["data"]["id"]
        resp = client.post(
            f"/api/v1/hotword/groups/{group_id}/words/bulk",
            json={"words": [{"word": f"客戶{i}"} for i in range(50)]},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["inserted_count"] == 50
    assert data["new_word_count"] == 50
    assert data["strategy"] == "shallow_fusion"


def test_bulk_upload_ctc_ws(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/hotword/groups", json={"name": "medium"}, headers=_headers(token))
        group_id = create_resp.json()["data"]["id"]
        resp = client.post(
            f"/api/v1/hotword/groups/{group_id}/words/bulk",
            json={"words": [{"word": f"w{i}"} for i in range(500)]},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["strategy"] == "ctc_ws"


def test_bulk_upload_too_large(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post("/api/v1/hotword/groups", json={"name": "huge"}, headers=_headers(token))
        group_id = create_resp.json()["data"]["id"]
        resp = client.post(
            f"/api/v1/hotword/groups/{group_id}/words/bulk",
            json={"words": [{"word": f"w{i}"} for i in range(1000)]},
            headers=_headers(token),
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "HOTWORD_TOO_LARGE"


def test_unauthenticated_returns_401(hotword_app) -> None:
    app, _ = hotword_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/hotword/groups")
    assert resp.status_code == 401
