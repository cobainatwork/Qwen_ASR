"""startup_checks 單元測試。

使用 tmp_path fixture 避免依賴真實檔案系統路徑，
使用 monkeypatch 替換 create_engine 以跳過真實 DB 連線。
"""

import pytest
from app.core.config import Settings
from app.core.startup_checks import run_startup_checks


def _make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "API_KEY": "k",
        "DATABASE_URL": "postgresql+psycopg://u:p@invalid-host/d",
        "DB_PASSWORD": "p",
        "THIRD_PARTY_LICENSE_ACK": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_license_ack_false_exits(tmp_path: pytest.TempPathFactory) -> None:
    """THIRD_PARTY_LICENSE_ACK=False 必須 sys.exit。"""
    s = _make_settings(THIRD_PARTY_LICENSE_ACK=False, AUDIO_STORAGE_DIR=tmp_path)
    with pytest.raises(SystemExit, match="THIRD_PARTY_LICENSE_ACK"):
        run_startup_checks(s)


def test_production_requires_docs_auth(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production 環境未設 OPENAPI_DOCS_REQUIRE_AUTH=true 必須 sys.exit。"""

    class _FakeConn:
        def __enter__(self) -> "_FakeConn":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def execute(self, *args: object) -> None:
            pass

    class _FakeEngine:
        def connect(self) -> _FakeConn:
            return _FakeConn()

        def dispose(self) -> None:
            pass

    monkeypatch.setattr(
        "app.core.startup_checks.create_engine",
        lambda *a, **kw: _FakeEngine(),
    )
    s = _make_settings(
        ENV="production",
        OPENAPI_DOCS_REQUIRE_AUTH=False,
        AUDIO_STORAGE_DIR=tmp_path,
    )
    with pytest.raises(SystemExit, match="OPENAPI_DOCS_REQUIRE_AUTH"):
        run_startup_checks(s)


def test_db_connection_failure_exits(tmp_path: pytest.TempPathFactory) -> None:
    """無效 DB 連線必須 sys.exit 並顯示「資料庫連線失敗」。"""
    s = _make_settings(AUDIO_STORAGE_DIR=tmp_path)
    with pytest.raises(SystemExit, match="資料庫連線失敗"):
        run_startup_checks(s)
