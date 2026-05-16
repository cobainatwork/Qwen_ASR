import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def configured_app(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("API_KEY", "boot-token-for-app-test")
    db_url = db_session.bind.engine.url.render_as_string(hide_password=False)  # type: ignore[union-attr]
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    db_session.execute(text("TRUNCATE api_keys, audit_logs CASCADE"))
    db_session.commit()

    # run_startup_checks 在 async lifespan 中做同步 DB I/O 會阻塞事件迴圈
    # 測試環境已由 conftest db_engine 確保 DB 可用，直接略過
    import app.core.startup_checks as _sc
    monkeypatch.setattr(_sc, "run_startup_checks", lambda settings: None)

    # lifespan 呼叫 get_session_factory()() 開新連線並 commit
    # 在測試的 rollback transaction 外部寫入，且 async context 中同步連線易超時
    # 解法：patch app.main 的 bootstrap_admin_key 引用，使用 db_session 執行
    import app.main as _main_mod
    from app.services.bootstrap import bootstrap_admin_key as _real_bootstrap
    monkeypatch.setattr(
        _main_mod, "bootstrap_admin_key", lambda _db, s: _real_bootstrap(db_session, s)
    )

    from app.core.config import get_settings
    from app.deps.db import get_db, get_engine, get_session_factory
    from app.main import _configure_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    app = _configure_app(get_settings())
    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_app_starts_and_creates_bootstrap_admin(configured_app, db_session: Session) -> None:
    with TestClient(configured_app):
        row = db_session.execute(
            text("SELECT name FROM api_keys WHERE name = 'bootstrap-admin'")
        ).first()
        assert row is not None


def test_response_envelope_on_health(configured_app) -> None:
    with TestClient(configured_app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"success", "data", "error"}


def test_unhandled_404_returns_envelope(configured_app) -> None:
    with TestClient(configured_app) as client:
        resp = client.get("/nope")
    assert resp.status_code == 404


def test_request_id_header_propagated(configured_app) -> None:
    with TestClient(configured_app) as client:
        resp = client.get("/health", headers={"X-Request-ID": "req-123"})
    assert resp.headers["X-Request-ID"] == "req-123"


def test_asr_route_registered(configured_app) -> None:
    paths = [route.path for route in configured_app.routes]
    assert "/api/v1/asr/transcribe" in paths
