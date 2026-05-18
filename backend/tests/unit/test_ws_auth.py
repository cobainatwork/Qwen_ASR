import base64

import pytest
from app.core.exceptions import WsAuthFailedError
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.services.ws_quality.auth import authenticate_websocket, parse_subprotocols
from sqlalchemy import text
from sqlalchemy.orm import Session


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def test_parse_valid_subprotocols() -> None:
    header = f"asr.v1, bearer.{_b64url('test-token-123')}"
    asr_v1, token = parse_subprotocols(header)
    assert asr_v1 is True
    assert token == "test-token-123"


def test_parse_missing_asr_v1() -> None:
    header = f"bearer.{_b64url('t')}"
    asr_v1, token = parse_subprotocols(header)
    assert asr_v1 is False
    assert token == "t"


def test_parse_no_bearer() -> None:
    header = "asr.v1"
    asr_v1, token = parse_subprotocols(header)
    assert asr_v1 is True
    assert token is None


def test_parse_empty_header() -> None:
    asr_v1, token = parse_subprotocols(None)
    assert asr_v1 is False
    assert token is None
    asr_v1, token = parse_subprotocols("")
    assert asr_v1 is False
    assert token is None


def test_parse_malformed_b64() -> None:
    with pytest.raises(WsAuthFailedError, match="無法解析"):
        parse_subprotocols("asr.v1, bearer.!!!malformed!!!")


def test_authenticate_success(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "ws-auth-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ws-real-token"
    settings = get_settings()
    hmac_key = derive_hmac_key("ws-auth-test")
    db_session.execute(text("TRUNCATE api_keys CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'wsk', '{asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()

    header = f"asr.v1, bearer.{_b64url(raw_token)}"
    api_key = authenticate_websocket(header, db_session, settings)
    assert api_key.name == "wsk"


def test_authenticate_missing_asr_v1(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(WsAuthFailedError, match=r"asr\.v1"):
        authenticate_websocket(f"bearer.{_b64url('t')}", db_session, get_settings())


def test_authenticate_invalid_token(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    db_session.execute(text("TRUNCATE api_keys CASCADE"))
    db_session.commit()

    header = f"asr.v1, bearer.{_b64url('fake-token')}"
    with pytest.raises(WsAuthFailedError, match="token 無效"):
        authenticate_websocket(header, db_session, get_settings())


def test_authenticate_missing_bearer(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """asr.v1 在但 bearer 缺：補回認證流程的對稱分支（reviewer 找到的覆蓋缺口）。"""
    monkeypatch.setenv("API_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(WsAuthFailedError, match="bearer"):
        authenticate_websocket("asr.v1", db_session, get_settings())
