from datetime import UTC, datetime, timedelta

import pytest
from app.core.exceptions import AppException
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def real_token_setup(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    monkeypatch.setenv("API_KEY", "bootstrap-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@h/d")
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "real-token-abcd"
    hmac_key = derive_hmac_key("bootstrap-test")
    prefix = lookup_prefix(raw_token, hmac_key)
    h = hash_token(raw_token)

    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'k', '{asr:read,asr:write}')"
        ),
        {"h": h, "p": prefix},
    )
    db_session.commit()
    key_id = int(db_session.execute(text("SELECT id FROM api_keys WHERE name = 'k'")).first()[0])
    return raw_token, key_id


def _app_with_override(db_session: Session) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _h(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"error": exc.code})

    @app.get("/protected")
    def protected(_: ApiKey = Depends(require_scope("asr:read"))) -> dict:  # noqa: B008
        return {"ok": True}

    @app.get("/admin-only")
    def admin_only(_: ApiKey = Depends(require_scope("admin"))) -> dict:  # noqa: B008
        return {"ok": True}

    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_missing_bearer_returns_401(db_session: Session) -> None:
    app = _app_with_override(db_session)
    resp = TestClient(app).get("/protected")
    assert resp.status_code == 401


def test_valid_token_returns_200(
    db_session: Session, real_token_setup: tuple[str, int]
) -> None:
    raw_token, _ = real_token_setup
    app = _app_with_override(db_session)
    resp = TestClient(app).get(
        "/protected", headers={"Authorization": f"Bearer {raw_token}"}
    )
    assert resp.status_code == 200


def test_wrong_scope_returns_403(
    db_session: Session, real_token_setup: tuple[str, int]
) -> None:
    raw_token, _ = real_token_setup
    app = _app_with_override(db_session)
    resp = TestClient(app).get(
        "/admin-only", headers={"Authorization": f"Bearer {raw_token}"}
    )
    assert resp.status_code == 403


def test_invalid_token_returns_401(db_session: Session) -> None:
    app = _app_with_override(db_session)
    resp = TestClient(app).get(
        "/protected", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401


def _seed_token_with_expires(
    db_session: Session,
    name: str,
    raw_token: str,
    expires_at: datetime,
) -> None:
    """插入一筆 api_key 並設定 expires_at（綁定參數，避免字串拼接）。"""
    hmac_key = derive_hmac_key("bootstrap-test")
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes, expires_at) "
            "VALUES (:h, :p, :n, '{asr:read,asr:write}', :e)"
        ),
        {
            "h": hash_token(raw_token),
            "p": lookup_prefix(raw_token, hmac_key),
            "n": name,
            "e": expires_at,
        },
    )
    db_session.commit()


def test_expired_token_returns_401(
    db_session: Session, real_token_setup: tuple[str, int]
) -> None:
    """expires_at 已過 → 401（規格 §19.1 line 2740：已過期同回 401）。"""
    expired_token = "expired-token-xyz"
    _seed_token_with_expires(
        db_session,
        "expired-k",
        expired_token,
        datetime.now(UTC) - timedelta(days=1),
    )
    app = _app_with_override(db_session)
    resp = TestClient(app).get(
        "/protected", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp.status_code == 401, resp.text


def test_future_expires_token_returns_200(
    db_session: Session, real_token_setup: tuple[str, int]
) -> None:
    """expires_at 在未來 → 仍可認證。"""
    future_token = "future-expires-token-abc"
    _seed_token_with_expires(
        db_session,
        "future-k",
        future_token,
        datetime.now(UTC) + timedelta(days=1),
    )
    app = _app_with_override(db_session)
    resp = TestClient(app).get(
        "/protected", headers={"Authorization": f"Bearer {future_token}"}
    )
    assert resp.status_code == 200, resp.text
