"""Integration tests for /ws/quality WebSocket endpoint (M10 T10.4).

Covers:
- Authenticated handshake + ping/pong (happy path).
- Missing asr.v1 subprotocol rejected (1008).
- Invalid bearer token rejected (1008).
- Exceeding WS_MAX_CONNECTIONS_PER_KEY rejected (1013).
- Unknown action returns ack with Phase 3 note.
- stream.start returns stream.unavailable with limitations list.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Iterator

import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.services.ws_quality import WebSocketManager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.testclient import TestClient


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


@pytest.fixture
def ws_app(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, str]]:
    monkeypatch.setenv("API_KEY", "ws-int-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("WS_MAX_CONNECTIONS_PER_KEY", "2")
    monkeypatch.setenv("WS_HEARTBEAT_TIMEOUT_SEC", "3")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ws-int-token"
    hmac_key = derive_hmac_key("ws-int-test")
    db_session.execute(text("DELETE FROM api_keys WHERE name = 'wsint'"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'wsint', '{asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()

    from app.routers.ws import router as ws_router
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ws_router)
    app.dependency_overrides[get_db] = lambda: db_session

    yield app, raw_token

    asyncio.run(WebSocketManager.reset_for_test())
    db_session.execute(text("DELETE FROM api_keys WHERE name = 'wsint'"))
    db_session.commit()


def test_ws_authenticated_handshake_and_ping_pong(ws_app: tuple[FastAPI, str]) -> None:
    app, token = ws_app
    sub = ["asr.v1", f"bearer.{_b64url(token)}"]
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=sub) as ws:
            connected = json.loads(ws.receive_text())
            assert connected["action"] == "connected"
            assert "connection_id" in connected
            ws.send_text(json.dumps({"action": "ping"}))
            data = json.loads(ws.receive_text())
            assert data["action"] == "pong"


def test_ws_missing_asr_v1_rejected(ws_app: tuple[FastAPI, str]) -> None:
    app, token = ws_app
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/ws/quality", subprotocols=[f"bearer.{_b64url(token)}"]
            ) as ws:
                ws.receive_text()
        assert exc.value.code == 1008


def test_ws_invalid_token_rejected(ws_app: tuple[FastAPI, str]) -> None:
    app, _ = ws_app
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/ws/quality", subprotocols=["asr.v1", f"bearer.{_b64url('fake')}"]
            ) as ws:
                ws.receive_text()
        assert exc.value.code == 1008


def test_ws_max_connections_close_1013(ws_app: tuple[FastAPI, str]) -> None:
    app, token = ws_app
    sub = ["asr.v1", f"bearer.{_b64url(token)}"]
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=sub) as ws1:
            ws1.receive_text()  # consume "connected"
            with client.websocket_connect("/ws/quality", subprotocols=sub) as ws2:
                ws2.receive_text()
                with pytest.raises(WebSocketDisconnect) as exc:
                    with client.websocket_connect("/ws/quality", subprotocols=sub) as ws3:
                        ws3.receive_text()
                assert exc.value.code == 1013


def test_ws_unknown_action_returns_ack_with_phase3_note(ws_app: tuple[FastAPI, str]) -> None:
    app, token = ws_app
    sub = ["asr.v1", f"bearer.{_b64url(token)}"]
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=sub) as ws:
            ws.receive_text()  # consume "connected"
            ws.send_text(json.dumps({"action": "noop"}))
            data = json.loads(ws.receive_text())
            assert data["action"] == "ack"
            assert "Phase 3" in data.get("note", "")


def test_ws_stream_start_returns_unavailable(ws_app: tuple[FastAPI, str]) -> None:
    app, token = ws_app
    sub = ["asr.v1", f"bearer.{_b64url(token)}"]
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=sub) as ws:
            ws.receive_text()  # connected
            ws.send_text(json.dumps({"action": "stream.start"}))
            data = json.loads(ws.receive_text())
            assert data["action"] == "stream.unavailable"
            assert isinstance(data.get("limitations"), list)
            assert any("timestamps" in lim for lim in data["limitations"])


def test_ws_insufficient_scope_rejected(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Key 持有 asr:read 但缺 asr:write：scope 檢查失敗，close(1008)。"""
    monkeypatch.setenv("API_KEY", "ws-scope-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("WS_MAX_CONNECTIONS_PER_KEY", "2")
    monkeypatch.setenv("WS_HEARTBEAT_TIMEOUT_SEC", "3")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ws-readonly-token"
    hmac_key = derive_hmac_key("ws-scope-test")
    db_session.execute(text("DELETE FROM api_keys WHERE name = 'wsread'"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'wsread', '{asr:read}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    try:
        from app.routers.ws import router as ws_router
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(ws_router)
        app.dependency_overrides[get_db] = lambda: db_session

        sub = ["asr.v1", f"bearer.{_b64url(raw_token)}"]
        from starlette.websockets import WebSocketDisconnect
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/ws/quality", subprotocols=sub) as ws:
                    ws.receive_text()
            assert exc.value.code == 1008
    finally:
        asyncio.run(WebSocketManager.reset_for_test())
        db_session.execute(text("DELETE FROM api_keys WHERE name = 'wsread'"))
        db_session.commit()


def test_ws_admin_scope_accepts_connection(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """admin scope 為 wildcard，與 deps/auth.py require_scope 同邏輯：admin 滿足任何 scope 需求。"""
    monkeypatch.setenv("API_KEY", "ws-admin-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("WS_MAX_CONNECTIONS_PER_KEY", "2")
    monkeypatch.setenv("WS_HEARTBEAT_TIMEOUT_SEC", "3")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ws-admin-token"
    hmac_key = derive_hmac_key("ws-admin-test")
    db_session.execute(text("DELETE FROM api_keys WHERE name = 'wsadm'"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'wsadm', '{admin}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    try:
        from app.routers.ws import router as ws_router
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(ws_router)
        app.dependency_overrides[get_db] = lambda: db_session

        sub = ["asr.v1", f"bearer.{_b64url(raw_token)}"]
        with TestClient(app) as client:
            with client.websocket_connect("/ws/quality", subprotocols=sub) as ws:
                connected = json.loads(ws.receive_text())
                assert connected["action"] == "connected"
                assert "connection_id" in connected
    finally:
        asyncio.run(WebSocketManager.reset_for_test())
        db_session.execute(text("DELETE FROM api_keys WHERE name = 'wsadm'"))
        db_session.commit()
