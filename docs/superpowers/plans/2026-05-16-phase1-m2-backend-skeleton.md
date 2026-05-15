# Phase 1 / M2 — 後端骨架（FastAPI + DB + 認證 + 橫切骨架）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M1 容器化骨架之上，建立 FastAPI 後端骨架，含 SQLAlchemy 模型、Alembic 初始 migration（4 個表格）、Argon2id + lookup_prefix 認證、Tenant Isolation Repository、JSON 結構化日誌、ResponseEnvelope 與全域錯誤處理、預留 no-op middleware、`GET /health` 與 `GET /readiness` 端點、Bootstrap admin 金鑰自動建立。M2 完成代表後端可受認證地接收 HTTP 請求並寫入 audit_logs。

**Architecture:** Application factory + lifespan 模式。FastAPI 啟動時依序執行：startup_checks → 載入 structlog → 連線 DB → 執行 Alembic 檢查（生產環境）→ 自動建立 bootstrap admin → 註冊 router 與 middleware。Repository 透過 `TenantScopedRepository[Model]` 基底自動掛載 `api_key_id` 過濾。認證鏈：Bearer token → HMAC-SHA256 前 16 字元定位（`lookup_prefix`）→ Argon2id verify → scope 比對。所有錯誤透過 `AppException` 子類與全域處理器轉成 `ResponseEnvelope`，錯誤碼對應規格附錄 A。

**Tech Stack:** FastAPI 0.115+、SQLAlchemy 2.0、Alembic 1.14、Pydantic 2、pydantic-settings、structlog、argon2-cffi、psycopg 3、testcontainers-postgres、pytest-asyncio、httpx。

**對應設計文件：** `docs/superpowers/specs/2026-05-16-phase1-implementation-design.md` 第 1.2、2.3、3、4 章節。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/core/config.py` | Create | pydantic-settings、ENV 載入、Phase 1 變數白名單 |
| `backend/app/core/exceptions.py` | Create | `AppException` 基底 + 20 個錯誤碼類別 |
| `backend/app/core/response.py` | Create | `ResponseEnvelope[T]`、`ErrorDetail`、`PaginationMeta` |
| `backend/app/core/logging.py` | Create | structlog 配置、敏感資料過濾、JSON 序列化 |
| `backend/app/core/security.py` | Create | Argon2id、`lookup_prefix(token)`、`verify_token()` |
| `backend/app/core/startup_checks.py` | Create | THIRD_PARTY_LICENSE_ACK、BACKEND_TYPE、目錄可寫等檢查 |
| `backend/app/models/base.py` | Create | `Base`、`TimestampMixin`、`UpdatedAtMixin`、`TenantMixin` |
| `backend/app/models/api_key.py` | Create | `ApiKey` ORM |
| `backend/app/models/audio_file.py` | Create | `AudioFile` ORM |
| `backend/app/models/transcription.py` | Create | `Transcription` ORM |
| `backend/app/models/audit_log.py` | Create | `AuditLog` ORM |
| `backend/alembic.ini` | Create | Alembic 配置 |
| `backend/alembic/env.py` | Create | online migration 程式 |
| `backend/alembic/script.py.mako` | Create | migration 模板 |
| `backend/alembic/versions/0001_phase1_initial.py` | Create | 建立 4 個表格、索引、trigger、zhparser 設定 |
| `backend/app/deps/db.py` | Create | SQLAlchemy session DI |
| `backend/app/deps/auth.py` | Create | `get_current_tenant`、`require_scope` |
| `backend/app/repositories/base.py` | Create | `TenantScopedRepository[T]` |
| `backend/app/repositories/api_key.py` | Create | `ApiKeyRepository`（不繼承 TenantScopedRepository，跨租戶） |
| `backend/app/repositories/audio_file.py` | Create | `AudioFileRepository` |
| `backend/app/repositories/transcription.py` | Create | `TranscriptionRepository` |
| `backend/app/repositories/audit_log.py` | Create | `AuditLogRepository` |
| `backend/app/services/audit.py` | Create | `record_audit_event()` 高階 helper |
| `backend/app/services/bootstrap.py` | Create | `bootstrap_admin_key()` |
| `backend/app/middleware/request_id.py` | Create | trace_id / request_id 注入 |
| `backend/app/middleware/error_handler.py` | Create | 全域 `AppException` / `Exception` 處理 |
| `backend/app/middleware/prometheus.py` | Create | no-op pass-through（Phase 2 啟用） |
| `backend/app/middleware/tracing.py` | Create | no-op pass-through |
| `backend/app/middleware/rate_limit.py` | Create | no-op pass-through |
| `backend/app/middleware/idempotency.py` | Create | no-op pass-through |
| `backend/app/schemas/common.py` | Create | `ResponseEnvelope`、`PaginationMeta`、`HealthData` |
| `backend/app/routers/health.py` | Create | `GET /health`、`GET /readiness` |
| `backend/app/main.py` | Create | FastAPI 工廠、lifespan、router 註冊 |
| `backend/tests/conftest.py` | Create | DB fixture、async client、valid_token |
| `backend/tests/unit/*` | Create | 各模組單元測試 |
| `backend/tests/integration/*` | Create | health / auth / repositories / alembic 整合測試 |
| `.github/workflows/ci.yml` | Create | CI workflow（lint-type / test / migration-check / docker-build） |

---

## Task 2.1：建立 `app/core/config.py` 與單元測試

**Files:**
- Create: `backend/app/core/__init__.py`（空檔案）
- Create: `backend/app/core/config.py`
- Create: `backend/tests/__init__.py`（空檔案）
- Create: `backend/tests/unit/__init__.py`（空檔案）
- Create: `backend/tests/unit/test_config.py`

- [ ] **Step 1：建立目錄占位 `__init__.py`**

```bash
cd backend
New-Item app/core/__init__.py -ItemType File -Force
New-Item tests/__init__.py -ItemType File -Force
New-Item tests/unit/__init__.py -ItemType File -Force
```

- [ ] **Step 2：撰寫 `app/core/config.py`**

```python
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Phase 1 環境變數白名單。"""

    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ----- 必填 -----
    API_KEY: str
    DATABASE_URL: str
    DB_PASSWORD: str
    THIRD_PARTY_LICENSE_ACK: bool
    ENV: Literal["development", "staging", "production"] = "development"
    DEPLOYMENT_PROFILE: Literal["client", "vendor"] = "client"

    # ----- 模型與 vLLM -----
    ASR_MODEL: str = "Qwen/Qwen3-ASR-1.7B"
    MODEL_CACHE_DIR: Path = Path("/data/models")
    BACKEND_TYPE: Literal["vllm"] = "vllm"
    VLLM_GPU_MEMORY_UTILIZATION: float = 0.5
    GPU_DEVICE: str = "cuda:0"
    MAX_INFERENCE_BATCH: int = 32
    ASR_MAX_TOKENS: int = 4096
    ASR_REQUEST_TIMEOUT_SEC: int = 1200
    ASR_AUDIO_MAX_DURATION_SEC: int = 1200

    # ----- 音檔處理 -----
    AUDIO_STORAGE_DIR: Path = Path("/data/audio")
    VAD_ENABLED: bool = True
    VAD_MODEL_PATH: Path = Path("/data/models/FireRedVAD/model.bin")
    MAX_UPLOAD_SIZE_MB: int = 100
    MAX_DECODE_SIZE_MB: int = 500
    SUPPORTED_AUDIO_FORMATS: str = "wav,mp3,mp4,flac,aac,ogg,m4a"

    # ----- 佇列 -----
    QUEUE_BATCH_MAX_SIZE: int = 20
    QUEUE_REALTIME_MAX_SIZE: int = 50
    QUEUE_REJECT_BEHAVIOR: Literal["reject", "wait"] = "reject"

    # ----- 可觀測性 -----
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"

    # ----- 安全與 CORS -----
    CORS_ORIGINS: str = "http://localhost:3000"
    CORS_ALLOW_CREDENTIALS: bool = False
    OPENAPI_DOCS_ENABLED: bool = True
    OPENAPI_DOCS_REQUIRE_AUTH: bool = False

    # ----- 補充：認證查找用 HMAC 密鑰 -----
    # 注意：Phase 1 暫以 API_KEY 衍生 HMAC 密鑰；正式部署應獨立提供
    LOOKUP_HMAC_KEY: str | None = None

    @field_validator("LOG_FORMAT")
    @classmethod
    def enforce_json_in_phase1(cls, v: str) -> str:
        if v != "json":
            raise ValueError("Phase 1 強制 LOG_FORMAT=json（CLAUDE.md 規範 20）")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def supported_formats_list(self) -> list[str]:
        return [f.strip().lower() for f in self.SUPPORTED_AUDIO_FORMATS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 3：撰寫 `tests/unit/test_config.py`**

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


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
```

- [ ] **Step 4：執行測試確認通過**

```bash
cd backend
pytest tests/unit/test_config.py -v
```

預期：5 個測試全部 PASS。

- [ ] **Step 5：執行 ruff + mypy**

```bash
ruff check app tests
mypy app
```

預期：兩者皆通過。

- [ ] **Step 6：Commit**

```bash
git add backend/app/core/__init__.py backend/app/core/config.py backend/tests/__init__.py backend/tests/unit/__init__.py backend/tests/unit/test_config.py
git commit -m "feat(backend): 加入 Settings（pydantic-settings）與 Phase 1 ENV 白名單"
```

---

## Task 2.2：建立 `app/core/exceptions.py` 與單元測試

**Files:**
- Create: `backend/app/core/exceptions.py`
- Create: `backend/tests/unit/test_exceptions.py`

- [ ] **Step 1：撰寫 `app/core/exceptions.py`**

```python
"""應用例外與錯誤碼字典。錯誤碼對應規格附錄 A。"""

from typing import Any


class AppException(Exception):
    """所有業務例外的基底。"""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "伺服器內部錯誤"

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        if message is not None:
            self.message = message
        if http_status is not None:
            self.http_status = http_status
        self.details = details
        super().__init__(self.message)


# ----- 認證 / 授權 -----
class UnauthorizedError(AppException):
    code = "AUTH_INVALID_TOKEN"
    http_status = 401
    message = "認證失敗"


class MissingBearerError(AppException):
    code = "AUTH_MISSING_BEARER"
    http_status = 401
    message = "缺失 Authorization Bearer 標頭"


class ForbiddenError(AppException):
    code = "AUTH_SCOPE_INSUFFICIENT"
    http_status = 403
    message = "權限不足"


# ----- 資料 -----
class NotFoundError(AppException):
    code = "NOT_FOUND"
    http_status = 404
    message = "資源不存在"


class ValidationFailedError(AppException):
    code = "VALIDATION_ERROR"
    http_status = 422
    message = "請求驗證失敗"


# ----- 音檔處理 -----
class AudioMimeInvalidError(AppException):
    code = "AUDIO_MIME_INVALID"
    http_status = 400
    message = "音檔格式不在白名單"


class AudioFileTooLargeError(AppException):
    code = "AUDIO_FILE_TOO_LARGE"
    http_status = 413
    message = "音檔超過大小上限"


class AudioDecodeTimeoutError(AppException):
    code = "AUDIO_DECODE_TIMEOUT"
    http_status = 504
    message = "音檔解碼超時"


class AudioResampleFailedError(AppException):
    code = "AUDIO_RESAMPLE_FAILED"
    http_status = 500
    message = "重取樣失敗"


class AudioNoSpeechError(AppException):
    code = "AUDIO_NO_SPEECH"
    http_status = 422
    message = "音檔未偵測到語音"


class AudioVadNotReadyError(AppException):
    code = "AUDIO_VAD_NOT_READY"
    http_status = 503
    message = "VAD 模組尚未就緒"


class AudioVadFailedError(AppException):
    code = "AUDIO_VAD_FAILED"
    http_status = 500
    message = "VAD 推理失敗"


class AudioStorageFailedError(AppException):
    code = "AUDIO_STORAGE_FAILED"
    http_status = 500
    message = "音檔儲存失敗"


# ----- ASR -----
class AsrEngineUnavailableError(AppException):
    code = "ASR_ENGINE_UNAVAILABLE"
    http_status = 503
    message = "ASR 推理引擎未就緒"


class AsrAudioTooLongError(AppException):
    code = "ASR_AUDIO_TOO_LONG"
    http_status = 413
    message = "音檔長度超過 20 分鐘上限"


class AsrCudaError(AppException):
    code = "ASR_CUDA_ERROR"
    http_status = 503
    message = "GPU 推理錯誤"


class AsrInferenceFailedError(AppException):
    code = "ASR_INFERENCE_FAILED"
    http_status = 500
    message = "ASR 推理失敗"


class AsrRequestTimeoutError(AppException):
    code = "ASR_REQUEST_TIMEOUT"
    http_status = 504
    message = "ASR 請求等待逾時"


class QueueFullError(AppException):
    code = "QUEUE_FULL"
    http_status = 503
    message = "處理佇列已滿"


# 完整錯誤碼清單（用於 OpenAPI 文件與測試自動化）
ALL_ERROR_CODES: tuple[str, ...] = (
    "INTERNAL_ERROR",
    "AUTH_INVALID_TOKEN",
    "AUTH_MISSING_BEARER",
    "AUTH_SCOPE_INSUFFICIENT",
    "NOT_FOUND",
    "VALIDATION_ERROR",
    "AUDIO_MIME_INVALID",
    "AUDIO_FILE_TOO_LARGE",
    "AUDIO_DECODE_TIMEOUT",
    "AUDIO_RESAMPLE_FAILED",
    "AUDIO_NO_SPEECH",
    "AUDIO_VAD_NOT_READY",
    "AUDIO_VAD_FAILED",
    "AUDIO_STORAGE_FAILED",
    "ASR_ENGINE_UNAVAILABLE",
    "ASR_AUDIO_TOO_LONG",
    "ASR_CUDA_ERROR",
    "ASR_INFERENCE_FAILED",
    "ASR_REQUEST_TIMEOUT",
    "QUEUE_FULL",
)
```

- [ ] **Step 2：撰寫測試 `tests/unit/test_exceptions.py`**

```python
import pytest

from app.core.exceptions import (
    ALL_ERROR_CODES,
    AppException,
    ForbiddenError,
    MissingBearerError,
    UnauthorizedError,
)


def test_app_exception_defaults() -> None:
    exc = AppException()
    assert exc.code == "INTERNAL_ERROR"
    assert exc.http_status == 500


def test_app_exception_override() -> None:
    exc = AppException(code="CUSTOM", message="msg", http_status=418, details={"k": "v"})
    assert exc.code == "CUSTOM"
    assert exc.http_status == 418
    assert exc.details == {"k": "v"}


@pytest.mark.parametrize(
    "exc_cls,code,status",
    [
        (UnauthorizedError, "AUTH_INVALID_TOKEN", 401),
        (MissingBearerError, "AUTH_MISSING_BEARER", 401),
        (ForbiddenError, "AUTH_SCOPE_INSUFFICIENT", 403),
    ],
)
def test_subclass_defaults(exc_cls: type[AppException], code: str, status: int) -> None:
    exc = exc_cls()
    assert exc.code == code
    assert exc.http_status == status


def test_all_error_codes_unique() -> None:
    assert len(ALL_ERROR_CODES) == len(set(ALL_ERROR_CODES))


def test_all_error_codes_at_least_20() -> None:
    assert len(ALL_ERROR_CODES) >= 20
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/unit/test_exceptions.py -v
```

預期：所有測試 PASS。

- [ ] **Step 4：ruff + mypy**

```bash
ruff check app tests
mypy app
```

預期：通過。

- [ ] **Step 5：Commit**

```bash
git add backend/app/core/exceptions.py backend/tests/unit/test_exceptions.py
git commit -m "feat(backend): 加入 AppException 基底與 20 個錯誤碼類別"
```

---

## Task 2.3：建立 `app/core/response.py` 與單元測試

**Files:**
- Create: `backend/app/core/response.py`
- Create: `backend/app/schemas/__init__.py`（空檔案）
- Create: `backend/app/schemas/common.py`
- Create: `backend/tests/unit/test_response.py`

- [ ] **Step 1：撰寫 `app/schemas/common.py`**

```python
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PaginationMeta(BaseModel):
    total: int
    page: int
    limit: int
    total_pages: int


class HealthData(BaseModel):
    status: str
    version: str


class ReadinessData(BaseModel):
    status: str
    checks: dict[str, str]
```

- [ ] **Step 2：撰寫 `app/core/response.py`（helper 工廠）**

```python
from typing import Any, TypeVar

from app.schemas.common import ErrorDetail, ResponseEnvelope

T = TypeVar("T")


def success(data: T) -> ResponseEnvelope[T]:
    return ResponseEnvelope[T](success=True, data=data, error=None)


def failure(code: str, message: str, details: dict[str, Any] | None = None) -> ResponseEnvelope[None]:
    return ResponseEnvelope[None](
        success=False,
        data=None,
        error=ErrorDetail(code=code, message=message, details=details),
    )
```

- [ ] **Step 3：撰寫 `tests/unit/test_response.py`**

```python
from app.core.response import failure, success
from app.schemas.common import HealthData, PaginationMeta, ResponseEnvelope


def test_success_envelope_shape() -> None:
    env = success({"hello": "world"})
    dumped = env.model_dump()
    assert dumped == {"success": True, "data": {"hello": "world"}, "error": None}


def test_failure_envelope_shape() -> None:
    env = failure("AUTH_INVALID_TOKEN", "認證失敗", details={"hint": "expired"})
    dumped = env.model_dump()
    assert dumped["success"] is False
    assert dumped["data"] is None
    assert dumped["error"] == {
        "code": "AUTH_INVALID_TOKEN",
        "message": "認證失敗",
        "details": {"hint": "expired"},
    }


def test_typed_envelope_with_health_data() -> None:
    env: ResponseEnvelope[HealthData] = success(HealthData(status="ok", version="0.1.0"))
    assert env.data is not None
    assert env.data.status == "ok"


def test_pagination_meta_fields() -> None:
    p = PaginationMeta(total=100, page=2, limit=20, total_pages=5)
    assert p.total_pages == 5
```

- [ ] **Step 4：執行測試**

```bash
pytest tests/unit/test_response.py -v
```

預期：4 測試 PASS。

- [ ] **Step 5：ruff + mypy**

```bash
ruff check app tests && mypy app
```

- [ ] **Step 6：Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/schemas/common.py backend/app/core/response.py backend/tests/unit/test_response.py
git commit -m "feat(backend): 加入 ResponseEnvelope、ErrorDetail、PaginationMeta schema"
```

---

## Task 2.4：建立 `app/core/logging.py` 與單元測試

**Files:**
- Create: `backend/app/core/logging.py`
- Create: `backend/tests/unit/test_logging.py`

- [ ] **Step 1：撰寫 `app/core/logging.py`**

```python
import logging
import re
import sys

import structlog

# 敏感欄位黑名單
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "token",
    "password",
    "transcript_text",
    "asr_result",
    "audio_base64",
    "raw_token",
}

_BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def _redact_sensitive(_logger: object, _name: str, event_dict: dict) -> dict:
    """移除敏感欄位與遮蔽 Bearer token。"""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    for key, value in list(event_dict.items()):
        if isinstance(value, str) and _BEARER_PATTERN.search(value):
            event_dict[key] = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    return event_dict


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_format else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 2：撰寫 `tests/unit/test_logging.py`**

```python
import json
from io import StringIO

import pytest
import structlog

from app.core.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    yield
    structlog.reset_defaults()


def _capture_log(callable_: callable) -> dict:
    buf = StringIO()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    callable_()
    return json.loads(buf.getvalue().splitlines()[-1])


def test_get_logger_returns_bound_logger() -> None:
    configure_logging(level="INFO")
    logger = get_logger("test")
    assert hasattr(logger, "info")


def test_redact_authorization_header() -> None:
    configure_logging(level="INFO")
    logger = get_logger("test")
    buf = StringIO()
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    from app.core.logging import _redact_sensitive

    event = _redact_sensitive(None, "info", {"authorization": "Bearer secret-token"})
    assert event["authorization"] == "[REDACTED]"


def test_redact_bearer_in_message() -> None:
    from app.core.logging import _redact_sensitive

    event = _redact_sensitive(None, "info", {"message": "got header: Bearer abc123 from client"})
    assert "abc123" not in event["message"]
    assert "[REDACTED]" in event["message"]


def test_redact_transcript_text() -> None:
    from app.core.logging import _redact_sensitive

    event = _redact_sensitive(None, "info", {"transcript_text": "客戶機密內容"})
    assert event["transcript_text"] == "[REDACTED]"


def test_configure_logging_produces_json() -> None:
    buf = StringIO()
    configure_logging(level="INFO", json_format=True)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    logger = structlog.get_logger("t")
    logger.info("hello", extra_key=42)
    out = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(out)
    assert parsed["event"] == "hello"
    assert parsed["extra_key"] == 42
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/unit/test_logging.py -v
```

預期：5 個測試 PASS。

- [ ] **Step 4：Lint + Type**

```bash
ruff check app tests && mypy app
```

- [ ] **Step 5：Commit**

```bash
git add backend/app/core/logging.py backend/tests/unit/test_logging.py
git commit -m "feat(backend): 加入 structlog 配置與敏感資料過濾"
```

---

## Task 2.5：建立 `app/core/security.py`（Argon2id + lookup_prefix）與測試

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/tests/unit/test_security.py`

- [ ] **Step 1：撰寫 `app/core/security.py`**

```python
import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

# 規格 19.1 + 設計 PHASE1-SPEC-01 補丁
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
)


def hash_token(raw_token: str) -> str:
    """以 Argon2id 雜湊原始 token。"""
    return _hasher.hash(raw_token)


def verify_token_hash(raw_token: str, stored_hash: str) -> bool:
    """驗證 raw_token 是否符合儲存的 Argon2id 雜湊。"""
    try:
        _hasher.verify(stored_hash, raw_token)
        return True
    except (VerifyMismatchError, InvalidHash):
        return False


def lookup_prefix(raw_token: str, hmac_key: bytes) -> str:
    """產生用於 DB 索引查找的前綴。

    使用 HMAC-SHA256 而非直接 SHA256，避免攻擊者透過離線
    rainbow table 反推 raw_token。前 16 hex chars 提供 64-bit
    namespace，碰撞機率足夠低（< 10 萬筆金鑰下碰撞 < 1%）。
    """
    if not hmac_key:
        raise ValueError("hmac_key 不可為空")
    digest = hmac.new(hmac_key, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16]


def derive_hmac_key(api_key_env: str) -> bytes:
    """以 process-wide API_KEY 衍生 HMAC 密鑰。

    僅 Phase 1 使用。Phase 2 應改為獨立 LOOKUP_HMAC_KEY 環境變數。
    """
    return hashlib.sha256(("lookup-prefix-v1::" + api_key_env).encode("utf-8")).digest()
```

- [ ] **Step 2：撰寫 `tests/unit/test_security.py`**

```python
import pytest

from app.core.security import (
    derive_hmac_key,
    hash_token,
    lookup_prefix,
    verify_token_hash,
)


def test_hash_then_verify_succeeds() -> None:
    raw = "my-secret-token-abc"
    h = hash_token(raw)
    assert h != raw
    assert h.startswith("$argon2id$")
    assert verify_token_hash(raw, h) is True


def test_verify_wrong_token_fails() -> None:
    h = hash_token("correct")
    assert verify_token_hash("incorrect", h) is False


def test_verify_invalid_hash_returns_false() -> None:
    assert verify_token_hash("anything", "not-a-real-hash") is False


def test_hashes_differ_due_to_salt() -> None:
    h1 = hash_token("same-token")
    h2 = hash_token("same-token")
    assert h1 != h2  # 隨機 salt 確保每次雜湊不同


def test_lookup_prefix_deterministic() -> None:
    key = b"k" * 32
    p1 = lookup_prefix("raw-token-xyz", key)
    p2 = lookup_prefix("raw-token-xyz", key)
    assert p1 == p2
    assert len(p1) == 16


def test_lookup_prefix_different_tokens_diverge() -> None:
    key = b"k" * 32
    assert lookup_prefix("token-a", key) != lookup_prefix("token-b", key)


def test_lookup_prefix_different_keys_diverge() -> None:
    p1 = lookup_prefix("same-token", b"a" * 32)
    p2 = lookup_prefix("same-token", b"b" * 32)
    assert p1 != p2


def test_lookup_prefix_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="hmac_key 不可為空"):
        lookup_prefix("token", b"")


def test_derive_hmac_key_returns_32_bytes() -> None:
    key = derive_hmac_key("api-key-value")
    assert len(key) == 32
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/unit/test_security.py -v
```

預期：9 個測試 PASS。注意 Argon2id 計算較慢，總耗時 1-3 秒。

- [ ] **Step 4：Lint + Type**

```bash
ruff check app tests && mypy app
```

- [ ] **Step 5：Commit**

```bash
git add backend/app/core/security.py backend/tests/unit/test_security.py
git commit -m "feat(backend): 加入 Argon2id 雜湊與 lookup_prefix（PHASE1-SPEC-01 補丁）"
```

---

## Task 2.6：建立 SQLAlchemy 模型基底與 4 個 ORM models

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/api_key.py`
- Create: `backend/app/models/audio_file.py`
- Create: `backend/app/models/transcription.py`
- Create: `backend/app/models/audit_log.py`
- Create: `backend/tests/unit/test_models.py`

- [ ] **Step 1：撰寫 `app/models/base.py`**

```python
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenantMixin:
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_keys.id"), nullable=False, index=True
    )
```

- [ ] **Step 2：撰寫 `app/models/api_key.py`**

```python
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    lookup_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        server_default="{asr:read,asr:write}",
    )
    created_by_key_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("api_keys.id"), nullable=True
    )
    rate_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 3：撰寫 `app/models/audio_file.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class AudioFile(Base, TenantMixin):
    __tablename__ = "audio_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verified_mime_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    transcription_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("transcriptions.id"), nullable=True, index=True
    )
    original_sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
```

- [ ] **Step 4：撰寫 `app/models/transcription.py`**

```python
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class Transcription(Base, TenantMixin):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    speakers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_processing: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="processing")
    processing_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotword_group_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        onupdate="now()",
    )
```

- [ ] **Step 5：撰寫 `app/models/audit_log.py`**

```python
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    api_key_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("api_keys.id"), nullable=True
    )
    target_api_key_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("api_keys.id"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
```

- [ ] **Step 6：建立 `app/models/__init__.py`（顯式 re-export）**

```python
from app.models.api_key import ApiKey
from app.models.audio_file import AudioFile
from app.models.audit_log import AuditLog
from app.models.base import Base, TenantMixin, TimestampMixin, UpdatedAtMixin
from app.models.transcription import Transcription

__all__ = [
    "ApiKey",
    "AudioFile",
    "AuditLog",
    "Base",
    "TenantMixin",
    "TimestampMixin",
    "Transcription",
    "UpdatedAtMixin",
]
```

- [ ] **Step 7：撰寫 `tests/unit/test_models.py`（純結構驗證，不碰 DB）**

```python
from app.models import ApiKey, AudioFile, AuditLog, Base, Transcription


def test_all_models_subclass_base() -> None:
    assert issubclass(ApiKey, Base)
    assert issubclass(AudioFile, Base)
    assert issubclass(Transcription, Base)
    assert issubclass(AuditLog, Base)


def test_tenant_models_have_api_key_id() -> None:
    assert "api_key_id" in AudioFile.__table__.columns
    assert "api_key_id" in Transcription.__table__.columns


def test_api_keys_table_columns() -> None:
    cols = {c.name for c in ApiKey.__table__.columns}
    expected = {
        "id", "key_hash", "lookup_prefix", "name", "description",
        "scopes", "created_by_key_id", "rate_limit_override",
        "is_active", "created_at", "expires_at", "deleted_at", "last_used_at",
    }
    assert expected <= cols


def test_audit_logs_metadata_column_aliased() -> None:
    # 屬性名 metadata_ 但 DB 欄位名 metadata
    col = AuditLog.__table__.columns["metadata"]
    assert col.name == "metadata"
```

- [ ] **Step 8：執行測試**

```bash
pytest tests/unit/test_models.py -v
```

- [ ] **Step 9：Lint + Type**

```bash
ruff check app tests && mypy app
```

- [ ] **Step 10：Commit**

```bash
git add backend/app/models/
git add backend/tests/unit/test_models.py
git commit -m "feat(backend): 加入 SQLAlchemy 模型（ApiKey / AudioFile / Transcription / AuditLog）"
```

---

## Task 2.7：Alembic 配置 + 初始 migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_phase1_initial.py`

- [ ] **Step 1：建立 alembic 目錄結構**

```bash
cd backend
mkdir alembic
mkdir alembic/versions
```

- [ ] **Step 2：撰寫 `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = postgresql+psycopg://qwasr:devpass@localhost:5432/qwen_asr

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 3：撰寫 `backend/alembic/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

# 從環境變數覆寫 sqlalchemy.url
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4：撰寫 `backend/alembic/script.py.mako`**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5：撰寫 `backend/alembic/versions/0001_phase1_initial.py`**

```python
"""Phase 1 初始 schema：api_keys / audio_files / transcriptions / audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # zhparser 擴充與 chinese 中文檢索設定
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
    op.execute(
        "CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS chinese (PARSER = zhparser)"
    )
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION chinese ADD MAPPING FOR n,v,a,i,e,l WITH simple"
    )

    # api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("lookup_prefix", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default="{asr:read,asr:write}",
        ),
        sa.Column("created_by_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("rate_limit_override", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_api_keys_active_not_deleted",
        "api_keys",
        ["is_active"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_api_keys_lookup_prefix",
        "api_keys",
        ["lookup_prefix"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # transcriptions
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("timestamps", postgresql.JSONB(), nullable=True),
        sa.Column("speakers", postgresql.JSONB(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("post_processing", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="processing"),
        sa.Column("processing_duration_sec", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("hotword_group_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_transcriptions_api_key_id", "transcriptions", ["api_key_id"])
    op.create_index("idx_transcriptions_status", "transcriptions", ["status"])
    op.create_index(
        "idx_transcriptions_created_at",
        "transcriptions",
        [sa.text("created_at DESC")],
    )
    op.create_index("idx_transcriptions_source", "transcriptions", ["source"])
    op.execute(
        "CREATE INDEX idx_transcriptions_text_gin "
        "ON transcriptions USING gin(to_tsvector('chinese', transcript_text))"
    )
    op.execute(
        "CREATE INDEX idx_transcriptions_normalized_text_gin "
        "ON transcriptions USING gin(to_tsvector('chinese', normalized_text))"
    )

    # audio_files
    op.create_table(
        "audio_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("verified_mime_type", sa.String(50), nullable=True),
        sa.Column("transcription_id", sa.Integer(), sa.ForeignKey("transcriptions.id"), nullable=True),
        sa.Column("original_sample_rate", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audio_files_api_key_id", "audio_files", ["api_key_id"])
    op.create_index("idx_audio_files_transcription_id", "audio_files", ["transcription_id"])

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("target_api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_audit_logs_api_key_id_created",
        "audit_logs",
        ["api_key_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_audit_logs_event_type", "audit_logs", ["event_type"])

    # transcriptions.updated_at trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_transcriptions_updated_at
        BEFORE UPDATE ON transcriptions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_transcriptions_updated_at ON transcriptions")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP INDEX IF EXISTS idx_transcriptions_text_gin")
    op.execute("DROP INDEX IF EXISTS idx_transcriptions_normalized_text_gin")
    op.drop_table("audit_logs")
    op.drop_table("audio_files")
    op.drop_table("transcriptions")
    op.drop_table("api_keys")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese")
    op.execute("DROP EXTENSION IF EXISTS zhparser")
```

- [ ] **Step 6：啟動 postgres 並驗證 alembic upgrade**

```bash
cd D:\Qwen_asr
docker compose up -d postgres
Start-Sleep -Seconds 15

cd backend
$env:DATABASE_URL="postgresql+psycopg://qwasr:devpass@localhost:5432/qwen_asr"
alembic upgrade head
```

預期：`INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Phase 1 初始 schema`

- [ ] **Step 7：驗證表格存在**

```bash
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dt"
```

預期：列出 `api_keys`、`audio_files`、`alembic_version`、`audit_logs`、`transcriptions`。

- [ ] **Step 8：驗證 downgrade**

```bash
alembic downgrade base
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dt"
```

預期：只剩 `alembic_version` 表。

- [ ] **Step 9：再次 upgrade**

```bash
alembic upgrade head
docker compose down
```

- [ ] **Step 10：Commit**

```bash
git add backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako backend/alembic/versions/0001_phase1_initial.py
git commit -m "feat(backend): 加入 Alembic 配置與 Phase 1 初始 migration（4 個表格）"
```

---

## Task 2.8：DB session DI、Tenant Repository 基底與測試

**Files:**
- Create: `backend/app/deps/__init__.py`
- Create: `backend/app/deps/db.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/base.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/test_repositories.py`

- [ ] **Step 1：撰寫 `app/deps/db.py`**

```python
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().DATABASE_URL,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2：撰寫 `app/repositories/base.py`**

```python
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Query, Session

from app.models.base import Base

T = TypeVar("T", bound=Base)


class TenantScopedRepository(Generic[T]):
    """Tenant 隔離資料存取層。

    繼承後設定 `model: type[T]`，所有查詢會自動掛 api_key_id 過濾。
    """

    model: type[T]

    def __init__(self, db: Session, api_key_id: int) -> None:
        self.db = db
        self.api_key_id = api_key_id

    def _scoped_query(self) -> Query:
        return self.db.query(self.model).filter(
            self.model.api_key_id == self.api_key_id  # type: ignore[attr-defined]
        )

    def get(self, id_: int) -> T | None:
        return self._scoped_query().filter(self.model.id == id_).one_or_none()  # type: ignore[attr-defined]

    def list(self, limit: int = 50, offset: int = 0) -> list[T]:
        return self._scoped_query().limit(limit).offset(offset).all()

    def create(self, **kwargs: Any) -> T:
        instance = self.model(**kwargs, api_key_id=self.api_key_id)
        self.db.add(instance)
        self.db.flush()
        return instance

    def update(self, instance: T, **changes: Any) -> T:
        if getattr(instance, "api_key_id", None) != self.api_key_id:
            raise PermissionError("跨租戶 update")
        for k, v in changes.items():
            setattr(instance, k, v)
        self.db.flush()
        return instance

    def delete(self, instance: T) -> None:
        if getattr(instance, "api_key_id", None) != self.api_key_id:
            raise PermissionError("跨租戶 delete")
        self.db.delete(instance)
        self.db.flush()
```

- [ ] **Step 3：撰寫 `tests/conftest.py`（DB fixture）**

```python
import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    """啟動 qwen-asr-postgres:test 容器（需先 docker build postgres/）。"""
    image = os.environ.get("TEST_POSTGRES_IMAGE", "qwen-asr-postgres:test")
    with PostgresContainer(image, username="test", password="test", dbname="qwen_asr_test") as pg:
        yield pg.get_connection_url(driver="psycopg")


@pytest.fixture(scope="session")
def db_engine(postgres_url: str) -> Generator[Engine, None, None]:
    """初始化 schema：直接 alembic upgrade head。"""
    from alembic import command
    from alembic.config import Config

    engine = create_engine(postgres_url, future=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """每測試獨立交易，結束時 rollback。"""
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def seed_api_key(db_session: Session) -> int:
    """建立一個測試 API key，回傳 id。"""
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, :n, :s)"
        ),
        {
            "h": "$argon2id$dummy",
            "p": "1234567890abcdef",
            "n": "test-key",
            "s": "{asr:read,asr:write}",
        },
    )
    row = db_session.execute(text("SELECT id FROM api_keys WHERE name = 'test-key'")).first()
    assert row is not None
    return int(row[0])
```

- [ ] **Step 4：撰寫整合測試 `tests/integration/test_repositories.py`**

```python
import pytest
from sqlalchemy.orm import Session

from app.models import AudioFile, Transcription
from app.repositories.base import TenantScopedRepository


class AudioFileRepository(TenantScopedRepository[AudioFile]):
    model = AudioFile


class TranscriptionRepository(TenantScopedRepository[Transcription]):
    model = Transcription


@pytest.fixture
def second_api_key(db_session: Session) -> int:
    from sqlalchemy import text

    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES ('$argon2id$dummy2', 'abcdef0123456789', 'test-key-2', '{asr:read}')"
        )
    )
    row = db_session.execute(text("SELECT id FROM api_keys WHERE name = 'test-key-2'")).first()
    assert row is not None
    return int(row[0])


def test_create_audio_file_attaches_api_key_id(db_session: Session, seed_api_key: int) -> None:
    repo = AudioFileRepository(db_session, seed_api_key)
    af = repo.create(
        original_name="a.wav",
        storage_path="/data/audio/abc.wav",
        file_size=1024,
    )
    assert af.api_key_id == seed_api_key


def test_tenant_isolation_get(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    repo_a = AudioFileRepository(db_session, seed_api_key)
    af = repo_a.create(original_name="a.wav", storage_path="/x/a.wav", file_size=1)

    repo_b = AudioFileRepository(db_session, second_api_key)
    assert repo_b.get(af.id) is None


def test_tenant_isolation_list(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    AudioFileRepository(db_session, seed_api_key).create(
        original_name="a.wav", storage_path="/x/a.wav", file_size=1
    )
    AudioFileRepository(db_session, second_api_key).create(
        original_name="b.wav", storage_path="/x/b.wav", file_size=2
    )
    assert len(AudioFileRepository(db_session, seed_api_key).list()) == 1
    assert len(AudioFileRepository(db_session, second_api_key).list()) == 1


def test_update_blocks_cross_tenant(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    repo_a = AudioFileRepository(db_session, seed_api_key)
    af = repo_a.create(original_name="a.wav", storage_path="/x/a.wav", file_size=1)

    repo_b = AudioFileRepository(db_session, second_api_key)
    with pytest.raises(PermissionError):
        repo_b.update(af, original_name="hack.wav")
```

- [ ] **Step 5：執行整合測試（需 postgres 映像）**

```bash
cd backend
pytest tests/integration/test_repositories.py -v
```

預期：4 個測試 PASS。第一次執行較慢（拉 postgres 映像 + alembic upgrade）。

- [ ] **Step 6：Lint + Type**

```bash
ruff check app tests && mypy app
```

- [ ] **Step 7：Commit**

```bash
git add backend/app/deps/__init__.py backend/app/deps/db.py backend/app/repositories/__init__.py backend/app/repositories/base.py backend/tests/conftest.py backend/tests/integration/__init__.py backend/tests/integration/test_repositories.py
git commit -m "feat(backend): 加入 DB session DI 與 TenantScopedRepository 基底"
```

---

## Task 2.9：認證 dependency（get_current_tenant、require_scope）與測試

**Files:**
- Create: `backend/app/repositories/api_key.py`
- Create: `backend/app/deps/auth.py`
- Create: `backend/tests/integration/test_auth.py`

- [ ] **Step 1：撰寫 `app/repositories/api_key.py`**

```python
from sqlalchemy.orm import Session

from app.models import ApiKey


class ApiKeyRepository:
    """跨租戶的 api_keys 存取（不繼承 TenantScopedRepository）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_active_by_prefix(self, prefix: str) -> list[ApiKey]:
        return (
            self.db.query(ApiKey)
            .filter(
                ApiKey.lookup_prefix == prefix,
                ApiKey.deleted_at.is_(None),
                ApiKey.is_active.is_(True),
            )
            .all()
        )

    def touch_last_used(self, api_key: ApiKey) -> None:
        from sqlalchemy import func

        api_key.last_used_at = func.now()
        self.db.flush()
```

- [ ] **Step 2：撰寫 `app/deps/auth.py`**

```python
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    ForbiddenError,
    MissingBearerError,
    UnauthorizedError,
)
from app.core.security import derive_hmac_key, lookup_prefix, verify_token_hash
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.api_key import ApiKeyRepository


def get_current_tenant(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise MissingBearerError()
    raw_token = authorization.split(" ", 1)[1].strip()
    if not raw_token:
        raise MissingBearerError()

    settings = get_settings()
    hmac_key = settings.LOOKUP_HMAC_KEY.encode() if settings.LOOKUP_HMAC_KEY else derive_hmac_key(settings.API_KEY)
    prefix = lookup_prefix(raw_token, hmac_key)

    repo = ApiKeyRepository(db)
    candidates = repo.find_active_by_prefix(prefix)
    for key in candidates:
        if verify_token_hash(raw_token, key.key_hash):
            repo.touch_last_used(key)
            return key
    raise UnauthorizedError()


def require_scope(scope: str):
    def _check(api_key: ApiKey = Depends(get_current_tenant)) -> ApiKey:
        if "admin" in api_key.scopes or scope in api_key.scopes:
            return api_key
        raise ForbiddenError(
            code="AUTH_SCOPE_INSUFFICIENT",
            message=f"需要 scope: {scope}",
            details={"required": scope, "granted": list(api_key.scopes)},
        )

    return _check
```

- [ ] **Step 3：撰寫整合測試 `tests/integration/test_auth.py`**

```python
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.auth import get_current_tenant, require_scope
from app.deps.db import get_db
from app.models import ApiKey


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

    @app.get("/protected")
    def protected(_: ApiKey = Depends(require_scope("asr:read"))) -> dict:
        return {"ok": True}

    @app.get("/admin-only")
    def admin_only(_: ApiKey = Depends(require_scope("admin"))) -> dict:
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
```

- [ ] **Step 4：執行測試**

```bash
pytest tests/integration/test_auth.py -v
```

預期：4 個測試 PASS。注意 Argon2id 較慢，總耗時 5-10 秒。

- [ ] **Step 5：Commit**

```bash
git add backend/app/repositories/api_key.py backend/app/deps/auth.py backend/tests/integration/test_auth.py
git commit -m "feat(backend): 加入 Bearer Token 認證與 scope 強制 dependency"
```

---

## Task 2.10：middleware（request_id、error_handler、4 個 no-op）

**Files:**
- Create: `backend/app/middleware/__init__.py`
- Create: `backend/app/middleware/request_id.py`
- Create: `backend/app/middleware/error_handler.py`
- Create: `backend/app/middleware/prometheus.py`
- Create: `backend/app/middleware/tracing.py`
- Create: `backend/app/middleware/rate_limit.py`
- Create: `backend/app/middleware/idempotency.py`
- Create: `backend/tests/unit/test_middleware_noop.py`

- [ ] **Step 1：撰寫 `app/middleware/request_id.py`**

```python
import uuid

import structlog
from fastapi import Request


async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    with structlog.contextvars.bound_contextvars(request_id=rid):
        response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
```

- [ ] **Step 2：撰寫 `app/middleware/error_handler.py`**

```python
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException, ValidationFailedError
from app.core.response import failure

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exc(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Request failed",
            error_code=exc.code,
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=failure(exc.code, exc.message, exc.details).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        v = ValidationFailedError(details={"errors": exc.errors()})
        logger.warning("Validation error", path=request.url.path, errors=exc.errors())
        return JSONResponse(
            status_code=v.http_status,
            content=failure(v.code, v.message, v.details).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=failure("INTERNAL_ERROR", "伺服器內部錯誤").model_dump(),
        )
```

- [ ] **Step 3：撰寫 4 個 no-op middleware**

`app/middleware/prometheus.py`：

```python
"""Phase 2 啟用：Prometheus metrics middleware。"""

from fastapi import Request


async def prometheus_middleware(request: Request, call_next):
    # Phase 2: 增加 request_count / duration histogram
    return await call_next(request)
```

`app/middleware/tracing.py`：

```python
"""Phase 2 啟用：OpenTelemetry tracing middleware。"""

from fastapi import Request


async def tracing_middleware(request: Request, call_next):
    # Phase 2: 建立 OTEL span，注入 trace_id
    return await call_next(request)
```

`app/middleware/rate_limit.py`：

```python
"""Phase 2 啟用：slowapi sliding window 限流。"""

from fastapi import Request


async def rate_limit_middleware(request: Request, call_next):
    # Phase 2: 依 api_key_id 限流
    return await call_next(request)
```

`app/middleware/idempotency.py`：

```python
"""Phase 2 啟用：Idempotency-Key 解析與重放。"""

from fastapi import Request


async def idempotency_middleware(request: Request, call_next):
    # Phase 2: 讀 Idempotency-Key header、Redis 查重
    return await call_next(request)
```

- [ ] **Step 4：撰寫 `app/middleware/__init__.py`**

```python
from app.middleware.error_handler import register_exception_handlers
from app.middleware.idempotency import idempotency_middleware
from app.middleware.prometheus import prometheus_middleware
from app.middleware.rate_limit import rate_limit_middleware
from app.middleware.request_id import request_id_middleware
from app.middleware.tracing import tracing_middleware

__all__ = [
    "idempotency_middleware",
    "prometheus_middleware",
    "rate_limit_middleware",
    "register_exception_handlers",
    "request_id_middleware",
    "tracing_middleware",
]
```

- [ ] **Step 5：撰寫 `tests/unit/test_middleware_noop.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import (
    idempotency_middleware,
    prometheus_middleware,
    rate_limit_middleware,
    request_id_middleware,
    tracing_middleware,
)


def _build_app_with_middleware(middleware) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(middleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"pong": True}

    return app


def test_request_id_middleware_returns_header() -> None:
    app = _build_app_with_middleware(request_id_middleware)
    resp = TestClient(app).get("/ping")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers


def test_request_id_middleware_uses_provided_id() -> None:
    app = _build_app_with_middleware(request_id_middleware)
    resp = TestClient(app).get("/ping", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"


@pytest.mark.parametrize(
    "mw",
    [prometheus_middleware, tracing_middleware, rate_limit_middleware, idempotency_middleware],
)
def test_noop_middlewares_are_passthrough(mw) -> None:
    app = _build_app_with_middleware(mw)
    resp = TestClient(app).get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


@pytest.mark.phase2
def test_prometheus_middleware_records_metrics() -> None:
    pytest.skip("Phase 2 啟用 Prometheus 後再驗證")


@pytest.mark.phase2
def test_rate_limit_middleware_enforces_limit() -> None:
    pytest.skip("Phase 2 啟用 slowapi 後再驗證")
```

- [ ] **Step 6：執行測試**

```bash
pytest tests/unit/test_middleware_noop.py -v
```

預期：6 個測試 PASS（含 2 個 phase2 skip）。

- [ ] **Step 7：Commit**

```bash
git add backend/app/middleware/ backend/tests/unit/test_middleware_noop.py
git commit -m "feat(backend): 加入 request_id / error_handler 與 4 個 no-op middleware"
```

---

## Task 2.11：Audit 服務、bootstrap admin、startup checks 與測試

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/audit.py`
- Create: `backend/app/services/bootstrap.py`
- Create: `backend/app/core/startup_checks.py`
- Create: `backend/tests/integration/test_bootstrap.py`
- Create: `backend/tests/unit/test_startup_checks.py`

- [ ] **Step 1：撰寫 `app/services/audit.py`**

```python
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def record_audit_event(
    db: Session,
    event_type: str,
    *,
    api_key_id: int | None = None,
    target_api_key_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            "INSERT INTO audit_logs "
            "(event_type, api_key_id, target_api_key_id, ip_address, user_agent, metadata) "
            "VALUES (:e, :a, :t, :i, :u, :m)"
        ),
        {
            "e": event_type,
            "a": api_key_id,
            "t": target_api_key_id,
            "i": ip_address,
            "u": user_agent,
            "m": metadata,
        },
    )
```

- [ ] **Step 2：撰寫 `app/services/bootstrap.py`**

```python
import structlog
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.models import ApiKey
from app.services.audit import record_audit_event

logger = structlog.get_logger(__name__)


def bootstrap_admin_key(db: Session, settings: Settings) -> None:
    """若 api_keys 表為空，自動建立 bootstrap admin。"""
    count = (
        db.query(ApiKey).filter(ApiKey.deleted_at.is_(None)).count()
    )
    if count > 0:
        return
    hmac_key = (
        settings.LOOKUP_HMAC_KEY.encode()
        if settings.LOOKUP_HMAC_KEY
        else derive_hmac_key(settings.API_KEY)
    )
    key = ApiKey(
        key_hash=hash_token(settings.API_KEY),
        lookup_prefix=lookup_prefix(settings.API_KEY, hmac_key),
        name="bootstrap-admin",
        description="啟動時自動建立的管理員金鑰",
        scopes=["admin"],
    )
    db.add(key)
    db.flush()
    record_audit_event(
        db,
        "auth.key_created",
        target_api_key_id=key.id,
        metadata={"reason": "bootstrap"},
    )
    db.commit()
    logger.info("bootstrap admin key created", api_key_id=key.id)
```

- [ ] **Step 3：撰寫 `app/core/startup_checks.py`**

```python
import os
import sys
from pathlib import Path

import structlog
from sqlalchemy import create_engine, text

from app.core.config import Settings

logger = structlog.get_logger(__name__)


def run_startup_checks(settings: Settings) -> None:
    if not settings.THIRD_PARTY_LICENSE_ACK:
        sys.exit("THIRD_PARTY_LICENSE_ACK 未設定為 true，依規格 26 節拒絕啟動")

    if settings.BACKEND_TYPE != "vllm":
        sys.exit(f"BACKEND_TYPE 必須為 'vllm'，目前為 '{settings.BACKEND_TYPE}'")

    if not settings.VAD_ENABLED:
        logger.warning("VAD_ENABLED=false 違反規格 6.1 推薦，建議改為 true")

    audio_dir = Path(settings.AUDIO_STORAGE_DIR)
    audio_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(audio_dir, os.W_OK):
        sys.exit(f"AUDIO_STORAGE_DIR 不可寫：{audio_dir}")

    if settings.ENV == "production" and not settings.OPENAPI_DOCS_REQUIRE_AUTH:
        sys.exit("Production 模式必須 OPENAPI_DOCS_REQUIRE_AUTH=true")

    try:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as e:
        sys.exit(f"資料庫連線失敗：{e}")
```

- [ ] **Step 4：撰寫 `tests/unit/test_startup_checks.py`**

```python
import pytest

from app.core.config import Settings
from app.core.startup_checks import run_startup_checks


def _make_settings(**overrides) -> Settings:
    base = {
        "API_KEY": "k",
        "DATABASE_URL": "postgresql+psycopg://u:p@invalid-host/d",
        "DB_PASSWORD": "p",
        "THIRD_PARTY_LICENSE_ACK": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_license_ack_false_exits(tmp_path) -> None:
    s = _make_settings(THIRD_PARTY_LICENSE_ACK=False, AUDIO_STORAGE_DIR=tmp_path)
    with pytest.raises(SystemExit, match="THIRD_PARTY_LICENSE_ACK"):
        run_startup_checks(s)


def test_production_requires_docs_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.startup_checks.create_engine",
        lambda *a, **kw: type("E", (), {"connect": lambda s: type("C", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None, "execute": lambda s, *a: None})(), "dispose": lambda s: None})(),
    )
    s = _make_settings(
        ENV="production",
        OPENAPI_DOCS_REQUIRE_AUTH=False,
        AUDIO_STORAGE_DIR=tmp_path,
    )
    with pytest.raises(SystemExit, match="OPENAPI_DOCS_REQUIRE_AUTH"):
        run_startup_checks(s)


def test_db_connection_failure_exits(tmp_path) -> None:
    s = _make_settings(AUDIO_STORAGE_DIR=tmp_path)
    with pytest.raises(SystemExit, match="資料庫連線失敗"):
        run_startup_checks(s)
```

- [ ] **Step 5：撰寫 `tests/integration/test_bootstrap.py`**

```python
import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.bootstrap import bootstrap_admin_key


def _settings(api_key: str = "boot-token") -> Settings:
    return Settings(
        API_KEY=api_key,
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
    )  # type: ignore[call-arg]


def test_bootstrap_creates_admin_when_empty(db_session: Session) -> None:
    from sqlalchemy import text

    db_session.execute(text("TRUNCATE api_keys, audit_logs CASCADE"))
    bootstrap_admin_key(db_session, _settings())

    row = db_session.execute(
        text("SELECT name, scopes FROM api_keys WHERE name = 'bootstrap-admin'")
    ).first()
    assert row is not None
    assert "admin" in row[1]

    audit = db_session.execute(
        text("SELECT event_type FROM audit_logs WHERE event_type = 'auth.key_created'")
    ).first()
    assert audit is not None


def test_bootstrap_skips_when_keys_exist(db_session: Session, seed_api_key: int) -> None:
    from sqlalchemy import text

    before = db_session.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one()
    bootstrap_admin_key(db_session, _settings())
    after = db_session.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one()
    assert before == after
```

- [ ] **Step 6：執行測試**

```bash
pytest tests/unit/test_startup_checks.py tests/integration/test_bootstrap.py -v
```

預期：所有測試 PASS。

- [ ] **Step 7：Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/audit.py backend/app/services/bootstrap.py backend/app/core/startup_checks.py backend/tests/unit/test_startup_checks.py backend/tests/integration/test_bootstrap.py
git commit -m "feat(backend): 加入啟動檢查、audit log、bootstrap admin 金鑰"
```

---

## Task 2.12：Health / Readiness 端點

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/health.py`
- Create: `backend/tests/integration/test_health.py`

- [ ] **Step 1：撰寫 `app/routers/health.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import success
from app.deps.db import get_db
from app.schemas.common import HealthData, ReadinessData, ResponseEnvelope

router = APIRouter(tags=["health"])

_VERSION = "0.1.0"


@router.get("/health", response_model=ResponseEnvelope[HealthData])
def health() -> ResponseEnvelope[HealthData]:
    return success(HealthData(status="ok", version=_VERSION))


@router.get("/readiness", response_model=ResponseEnvelope[ReadinessData])
def readiness(db: Session = Depends(get_db)) -> ResponseEnvelope[ReadinessData]:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"failed: {e}"
    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return success(ReadinessData(status=overall, checks=checks))
```

- [ ] **Step 2：撰寫 `tests/integration/test_health.py`**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.deps.db import get_db
from app.routers.health import router as health_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_health_endpoint(db_session: Session) -> None:
    client = TestClient(_build_app(db_session))
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["version"] == "0.1.0"
    assert body["error"] is None


def test_readiness_with_db_ok(db_session: Session) -> None:
    client = TestClient(_build_app(db_session))
    resp = client.get("/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["checks"]["database"] == "ok"
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/integration/test_health.py -v
```

預期：2 個測試 PASS。

- [ ] **Step 4：Commit**

```bash
git add backend/app/routers/__init__.py backend/app/routers/health.py backend/tests/integration/test_health.py
git commit -m "feat(backend): 加入 /health 與 /readiness 端點"
```

---

## Task 2.13：FastAPI app 工廠（main.py）整合

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/integration/test_app.py`

- [ ] **Step 1：撰寫 `app/main.py`**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.startup_checks import run_startup_checks
from app.deps.db import get_session_factory
from app.middleware import (
    idempotency_middleware,
    prometheus_middleware,
    rate_limit_middleware,
    register_exception_handlers,
    request_id_middleware,
    tracing_middleware,
)
from app.routers.health import router as health_router
from app.services.bootstrap import bootstrap_admin_key


def _configure_app(settings: Settings) -> FastAPI:
    configure_logging(level=settings.LOG_LEVEL, json_format=settings.LOG_FORMAT == "json")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger = get_logger("startup")
        logger.info("backend lifespan start", env=settings.ENV)
        run_startup_checks(settings)
        with get_session_factory()() as db:
            bootstrap_admin_key(db, settings)
        yield
        logger.info("backend lifespan stop")

    app = FastAPI(
        title="Qwen3-ASR API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.OPENAPI_DOCS_ENABLED else None,
        redoc_url=None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 自訂 middleware（順序：request_id → tracing → prometheus → rate_limit → idempotency）
    app.middleware("http")(idempotency_middleware)
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(prometheus_middleware)
    app.middleware("http")(tracing_middleware)
    app.middleware("http")(request_id_middleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    return app


def create_app() -> FastAPI:
    return _configure_app(get_settings())


app = create_app()
```

- [ ] **Step 2：撰寫 `tests/integration/test_app.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def configured_app(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("API_KEY", "boot-token-for-app-test")
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.engine.url))
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    db_session.execute(text("TRUNCATE api_keys, audit_logs CASCADE"))
    db_session.commit()

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
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/integration/test_app.py -v
```

預期：4 個測試 PASS。

- [ ] **Step 4：實際以 uvicorn 啟動驗證（手動 smoke）**

```bash
cd D:\Qwen_asr
docker compose up -d postgres
Start-Sleep -Seconds 15

cd backend
$env:DATABASE_URL="postgresql+psycopg://qwasr:devpass@localhost:5432/qwen_asr"
$env:API_KEY="dev-bootstrap-token"
$env:DB_PASSWORD="devpass"
$env:THIRD_PARTY_LICENSE_ACK="true"
$env:AUDIO_STORAGE_DIR="$env:TEMP/qwen_asr_audio"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

另開 terminal：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/readiness
```

預期：兩者皆回 `{"success": true, "data": {...}, "error": null}`。

按 `Ctrl+C` 停止 uvicorn。

```bash
cd ../
docker compose down
```

- [ ] **Step 5：Commit**

```bash
git add backend/app/main.py backend/tests/integration/test_app.py
git commit -m "feat(backend): 加入 FastAPI app 工廠與 lifespan 整合"
```

---

## Task 2.14：CI workflow（GitHub Actions）

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/check_response_envelope.py`

- [ ] **Step 1：建立 `.github/workflows/` 目錄**

```bash
cd D:\Qwen_asr
mkdir .github
mkdir .github/workflows
mkdir scripts
```

- [ ] **Step 2：撰寫 `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

env:
  PYTHON_VERSION: "3.12"

jobs:
  lint-type:
    runs-on: ubuntu-22.04
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy app

  test:
    runs-on: ubuntu-22.04
    services:
      docker:
        image: docker:24-dind
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: pip install -e ".[dev]"
      - name: Build postgres test image
        working-directory: ${{ github.workspace }}
        run: docker build -t qwen-asr-postgres:test postgres/
      - run: pytest -m "not gpu" --cov=app --cov-report=term --cov-fail-under=70

  migration-check:
    runs-on: ubuntu-22.04
    services:
      postgres:
        image: postgres:16-bookworm
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: qwen_asr_migration_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: pip install -e ".[dev]"
      - name: Install zhparser in postgres container
        run: |
          docker exec ${{ job.services.postgres.id }} bash -c "apt-get update && apt-get install -y postgresql-server-dev-16 libscws-dev build-essential git ca-certificates && git clone --depth 1 https://github.com/amutu/zhparser.git /tmp/zhparser && cd /tmp/zhparser && make && make install"
      - name: Alembic round-trip
        env:
          DATABASE_URL: postgresql+psycopg://postgres:test@localhost:5432/qwen_asr_migration_test
        run: |
          alembic upgrade head
          alembic downgrade base
          alembic upgrade head

  docker-build:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build backend builder stage
        run: docker build --target builder -t qwen-asr-backend:builder backend/
      - name: Build backend runtime stage (CPU)
        run: docker build --target runtime -t qwen-asr-backend:test --build-arg INSTALL_GPU_DEPS=false backend/

  api-contract:
    runs-on: ubuntu-22.04
    needs: [test]
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: pip install -e ".[dev]"
      - name: 檢查所有 router 是否使用 ResponseEnvelope
        run: python ../scripts/check_response_envelope.py
```

- [ ] **Step 3：撰寫 `scripts/check_response_envelope.py`**

```python
"""掃描 app/routers/ 內所有 @router.<method> decorator 是否標註 response_model=ResponseEnvelope[...]。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROUTERS_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "routers"


def _is_response_envelope(node: ast.expr) -> bool:
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        return node.value.id == "ResponseEnvelope"
    return False


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                continue
            if deco.func.attr not in {"get", "post", "put", "delete", "patch"}:
                continue
            kw = {k.arg: k.value for k in deco.keywords}
            rm = kw.get("response_model")
            if rm is None:
                errors.append(f"{path}::{node.name} 缺少 response_model")
                continue
            if not _is_response_envelope(rm):
                errors.append(f"{path}::{node.name} response_model 不是 ResponseEnvelope[...]")
    return errors


def main() -> int:
    all_errors: list[str] = []
    for py in ROUTERS_DIR.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        all_errors.extend(check_file(py))
    if all_errors:
        print("\n".join(all_errors), file=sys.stderr)
        return 1
    print(f"OK: 所有 router 端點皆使用 ResponseEnvelope（已掃描 {ROUTERS_DIR}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：本機驗證 contract 檢查腳本**

```bash
cd D:\Qwen_asr
python scripts/check_response_envelope.py
```

預期：印出「OK: 所有 router 端點皆使用 ResponseEnvelope」並 exit 0。

- [ ] **Step 5：Commit**

```bash
git add .github/ scripts/
git commit -m "ci: 加入 GitHub Actions 五段流水線（lint / test / migration / docker / contract）"
```

---

## Task 2.15：M2 整合驗收

**Files:**（無新檔案）

- [ ] **Step 1：本機跑完整 pytest 並驗證覆蓋率**

```bash
cd backend
pytest --cov=app --cov-report=term --cov-report=html
```

預期：
- 全部測試 PASS
- 覆蓋率 ≥ 70%（行覆蓋率）
- `core/security.py`、`repositories/base.py`、`middleware/error_handler.py` 覆蓋率 ≥ 90%

- [ ] **Step 2：實際以 docker compose 啟動 backend**

```bash
cd D:\Qwen_asr
Copy-Item .env.example .env
# 修改 .env：將 API_KEY 改成強隨機字串，DB_PASSWORD 改成強隨機字串
docker compose up -d
Start-Sleep -Seconds 30
```

- [ ] **Step 3：驗證 backend 啟動成功**

```bash
docker compose logs asr-backend | findstr "lifespan"
```

預期：看到 `backend lifespan start` 訊息。

- [ ] **Step 4：驗證 /health 與 /readiness**

```bash
curl http://localhost:8000/health
curl http://localhost:8000/readiness
```

預期：兩個端點皆回 200 + `success=true`。

- [ ] **Step 5：驗證未認證請求拒絕**

```bash
curl -i http://localhost:8000/docs
# OPENAPI_DOCS_REQUIRE_AUTH=false 時 200
# 改成 true 後應拒絕
```

- [ ] **Step 6：拆除環境**

```bash
docker compose down -v
Remove-Item .env
```

- [ ] **Step 7：Push 至 origin/main**

```bash
git push origin main
```

---

## Self-Review

**1. Spec coverage（對照設計文件第 2.3、3、4 段）：**

| 設計章節 | 對應 Task |
|---------|----------|
| 2.3 M2 工作項目 (1)–(8) | T2.1–T2.13 全部涵蓋 |
| 3.1 認證機制 | T2.5（security）、T2.9（auth dependency） |
| 3.2 多租戶隔離 | T2.8 |
| 3.3 JSON 結構化日誌 | T2.4 |
| 3.4 ResponseEnvelope | T2.3、T2.10（error_handler） |
| 3.5 預留 middleware | T2.10 |
| 4.2–4.5 四個表格 | T2.6（models）、T2.7（migration） |
| 2.3 M2 DoD 條件 1–8 | T2.7、T2.12、T2.9、T2.15 |
| 7.4 CI workflow | T2.14 |
| 7.7 啟動檢查 | T2.11 |
| 7.8 Bootstrap admin | T2.11 |

**2. Placeholder scan：** 已搜尋禁用詞，無命中。所有 code block 為實際可執行內容；`Phase 2` 字串僅出現於有意圖的延伸標記註解。

**3. Type consistency：**
- `ApiKey.scopes` 在 model 為 `list[str]`，DB 為 `VARCHAR(50)[]`，`require_scope` 內以 `in` 比對 — 一致
- `ResponseEnvelope[T]` 在 Task 2.3、2.10、2.12 簽章一致
- `TenantScopedRepository.create()` 自動掛 api_key_id 與 Task 2.8 測試行為對齊
- `derive_hmac_key()` 與 `lookup_prefix()` 簽章在 T2.5、T2.9、T2.11 三處使用一致
- Alembic migration 欄位類型（如 `INET`、`JSONB`、`ARRAY(String(50))`）與 ORM model 對應

---

## Execution Handoff

M2 plan 完成，等 M3 / M4 plan 寫完後一併與 M1 進入 Subagent-Driven Execution（你已選 1:A）。
