import pytest
from app.core.config import Settings
from pydantic import ValidationError


def _base_env(**overrides: str) -> dict[str, str]:
    base = {
        "API_KEY": "test-key",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/d",
        "DB_PASSWORD": "p",
        "THIRD_PARTY_LICENSE_ACK": "true",
    }
    base.update(overrides)
    return base


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PYDANTIC_SETTINGS_NO_DOTENV", "1")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.API_KEY == "test-key"
    assert s.THIRD_PARTY_LICENSE_ACK is True
    assert s.BACKEND_TYPE == "vllm"


def test_settings_log_format_must_be_json(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env(LOG_FORMAT="text").items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "Phase 1 強制 LOG_FORMAT=json" in str(exc.value)


def test_cors_origins_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env(CORS_ORIGINS="http://a, http://b , http://c").items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.cors_origins_list == ["http://a", "http://b", "http://c"]


def test_supported_formats_lowercased(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env(SUPPORTED_AUDIO_FORMATS="WAV,MP3,FLAC").items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.supported_formats_list == ["wav", "mp3", "flac"]


def test_backend_type_locked_to_vllm(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env(BACKEND_TYPE="transformers").items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_ws_heartbeat_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.WS_HEARTBEAT_TIMEOUT_SEC == 90
    assert s.WS_MAX_MESSAGE_SIZE_MB == 50
    assert s.WS_MAX_CONNECTIONS_PER_KEY == 10
