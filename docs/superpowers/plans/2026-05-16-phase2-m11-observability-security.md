# Phase 2 / M11 — 可觀測性 + 安全控管 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 啟用 Prometheus 指標、OpenTelemetry tracing、Sliding Window 限流、CSP 與安全標頭、OpenAPI 文檔保護、軟刪除 + erase 端點，並補完 audit_logs 覆蓋。完成後 `GET /metrics` 暴露 Prometheus 格式、限流回應 X-RateLimit headers、CSP nonce 注入、`DELETE /api/v1/auth/keys/:id/erase` 徹底刪除。

**Architecture:** Prometheus / tracing / rate_limit 從 M2 既有 no-op middleware 升級為實裝版本，透過 `app/middleware/*_active.py` 替換並保留 no-op 為 fallback。CSP / 安全標頭 / OpenAPI 保護由新中介層 `security_headers.py` 統一注入。auth_admin router 提供軟刪除（M2 既有 model 欄位）+ erase（新增端點）。所有變動相容 Phase 1 的 lifespan 結構。

**Tech Stack:** prometheus_client 0.20+、opentelemetry-api / opentelemetry-instrumentation-fastapi、starlette middleware。

**對應設計文件：** Phase 2 design.md §3.7、§4.7、§4.8。對應規格：v1.9 §18、§19、§22、§25、強制規範 17。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/middleware/prometheus_active.py` | Create | 實裝 metrics 中介層 |
| `backend/app/middleware/tracing_active.py` | Create | OTel span 注入 |
| `backend/app/middleware/rate_limit_active.py` | Create | Sliding Window 限流 |
| `backend/app/middleware/security_headers.py` | Create | CSP / HSTS / X-Frame-Options |
| `backend/app/middleware/__init__.py` | Modify | 條件式 re-export |
| `backend/app/routers/metrics.py` | Create | `GET /metrics` |
| `backend/app/routers/auth_admin.py` | Create | 軟刪除 + erase |
| `backend/app/main.py` | Modify | 條件式載入 active / no-op middleware + custom docs |
| `backend/app/core/exceptions.py` | Modify | 新增 RATE_LIMIT_EXCEEDED |
| `backend/app/core/config.py` | Modify | 新增 6 個 ENV |
| `backend/app/services/audit.py` | Modify | 補 event_type 標準清單 |
| `backend/tests/unit/test_rate_limit.py` | Create | 限流邏輯單元 |
| `backend/tests/unit/test_security_headers.py` | Create | CSP / HSTS 注入 |
| `backend/tests/integration/test_metrics_endpoint.py` | Create | /metrics 端到端 |
| `backend/tests/integration/test_auth_admin.py` | Create | 軟刪除 / erase |
| `backend/pyproject.toml` | Modify | 補 prometheus / OTel 依賴 |

---

## Task 11.1：依賴 + exceptions + ENV

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/exceptions.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1：擴充 `pyproject.toml` dependencies**

讀取既有 `[project] dependencies` 區塊，在末尾加：

```toml
  "prometheus-client>=0.20.0",
  "opentelemetry-api>=1.27.0",
  "opentelemetry-sdk>=1.27.0",
  "opentelemetry-instrumentation-fastapi>=0.48b0",
  "opentelemetry-exporter-otlp>=1.27.0",
```

- [ ] **Step 2：擴充 `exceptions.py`**

```python
# ----- Phase 2 / M11 -----
class RateLimitExceededError(AppException):
    code = "RATE_LIMIT_EXCEEDED"
    http_status = 429
    message = "請求頻率超過上限"
```

`ALL_ERROR_CODES` 補 1 個（42 → 43）。

- [ ] **Step 3：擴充 `config.py` 6 個 ENV**

```python
    # ----- Phase 2 / M11 可觀測性 -----
    PROMETHEUS_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    RATE_LIMIT_DEFAULT_PER_MIN: int = 60
    SECURITY_HEADERS_ENABLED: bool = True
    CSP_POLICY: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    HSTS_MAX_AGE: int = 31536000  # 1 year
```

- [ ] **Step 4：安裝新依賴**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

預期：成功安裝 prometheus_client + OTel 套件群。

- [ ] **Step 5：ruff + mypy**

```powershell
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/pyproject.toml backend/app/core/exceptions.py backend/app/core/config.py
git commit -m "$(@'
feat(m11): 補 prometheus / OTel 依賴 + 1 錯誤碼 + 6 ENV

- pyproject.toml dependencies 加：
  - prometheus-client 0.20+
  - opentelemetry-api / sdk / instrumentation-fastapi / exporter-otlp
- exceptions：RateLimitExceededError（429）
- config 6 個 M11 ENV：
  - PROMETHEUS_ENABLED（預設 false，dev 不啟用）
  - OTEL_EXPORTER_OTLP_ENDPOINT
  - RATE_LIMIT_DEFAULT_PER_MIN（預設 60）
  - SECURITY_HEADERS_ENABLED（預設 true）
  - CSP_POLICY 完整字串
  - HSTS_MAX_AGE 預設 1 年

對應計劃：M11 Task 11.1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 11.2：Prometheus + Tracing active middleware

**Files:**
- Create: `backend/app/middleware/prometheus_active.py`
- Create: `backend/app/middleware/tracing_active.py`
- Create: `backend/app/routers/metrics.py`
- Modify: `backend/app/middleware/__init__.py`

- [ ] **Step 1：撰寫 `app/middleware/prometheus_active.py`**

```python
"""Prometheus metrics middleware（取代 M2 既有 no-op）。

採實裝版本，由 PROMETHEUS_ENABLED ENV 控制掛載。
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import RequestResponseEndpoint

# 全域 metric 物件
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP request counter",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


async def prometheus_active_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """記錄每個 HTTP request 的 count + latency。"""
    method = request.method
    endpoint = request.url.path
    start = time.monotonic()
    try:
        response = await call_next(request)
        duration = time.monotonic() - start
        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=str(response.status_code)).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)
        return response
    except Exception:
        duration = time.monotonic() - start
        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code="500").inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)
        raise
```

- [ ] **Step 2：撰寫 `app/middleware/tracing_active.py`**

```python
"""OpenTelemetry tracing middleware（取代 M2 既有 no-op）。"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

logger = structlog.get_logger(__name__)


def configure_tracing(otlp_endpoint: str | None) -> Any:
    """設定 OpenTelemetry tracer provider 與 OTLP exporter。

    回傳 tracer。失敗時 log + return None（不阻擋啟動）。
    """
    if not otlp_endpoint:
        return None
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
    except ImportError as e:
        logger.warning("opentelemetry not installed, tracing disabled", error=str(e))
        return None

    resource = Resource.create({"service.name": "qwen-asr-backend"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info("OTel tracing configured", endpoint=otlp_endpoint)
    return trace.get_tracer("qwen-asr-backend")


async def tracing_active_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """以 trace_id 注入 structlog context（後續 log 自動帶 trace_id）。"""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        return await call_next(request)

    tracer = trace.get_tracer("qwen-asr-backend")
    span_name = f"{request.method} {request.url.path}"
    with tracer.start_as_current_span(span_name) as span:
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x") if ctx.trace_id else None
        if trace_id:
            structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            return await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("trace_id")
```

- [ ] **Step 3：撰寫 `app/routers/metrics.py`**

```python
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus exposition format。

    豁免認證（與 /health / /readiness 同列豁免清單）。
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 4：擴充 `app/middleware/__init__.py`**

讀取既有 `__init__.py`，加入兩個 active middleware re-export：

```python
from app.middleware.prometheus_active import prometheus_active_middleware
from app.middleware.tracing_active import configure_tracing, tracing_active_middleware
```

`__all__` 補三項。

- [ ] **Step 5：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/middleware/prometheus_active.py backend/app/middleware/tracing_active.py backend/app/routers/metrics.py backend/app/middleware/__init__.py
git commit -m "$(@'
feat(m11): Prometheus + OTel tracing active middleware + /metrics 端點

- middleware/prometheus_active.py：
  - Counter http_requests_total（method / endpoint / status_code）
  - Histogram http_request_duration_seconds（11 個 bucket）
  - 異常時記 status_code=500 後 re-raise
- middleware/tracing_active.py：
  - configure_tracing(otlp_endpoint)：lifespan 啟動時呼叫，設 BatchSpanProcessor + OTLP gRPC exporter
  - tracing_active_middleware：每 request 一個 span，trace_id 透過 structlog.contextvars 注入後續 log
- routers/metrics.py：/metrics 端點（豁免認證、include_in_schema=False）

M2 既有 no-op 仍保留作為 dev fallback；main.py 依 PROMETHEUS_ENABLED 條件式載入。

對應計劃：M11 Task 11.2
對應規格：v1.9 §22

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 11.3：Sliding Window 限流

**Files:**
- Create: `backend/app/middleware/rate_limit_active.py`
- Create: `backend/tests/unit/test_rate_limit.py`

- [ ] **Step 1：撰寫 `app/middleware/rate_limit_active.py`**

```python
"""Sliding Window 限流（規格 §19.4）。

依 api_key_id 限流（可由 ApiKey.rate_limit_override 覆寫）。
Phase 2 採內存實作（單 worker，與 workers=1 一致）；
Phase 3 改 Redis 後可橫向擴展。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

# 全域內存儲存：api_key_id → deque[float] (timestamps)
_WINDOWS: dict[int, deque[float]] = {}
_LOCK = asyncio.Lock()
_WINDOW_SEC = 60.0


# 豁免路徑（規格約定不限流）
_EXEMPT_PATHS = frozenset({"/health", "/readiness", "/metrics"})


def _api_key_id_from_request(request: Request) -> int | None:
    """從 request.state 取出 api_key_id（在 auth dependency 解析後設置）。

    Phase 2：本中介層在 dependency 解析前執行，無法直接取得 api_key_id。
    採折衷：用 Bearer token hash 後 16 字元作為 rate-limit key（與 lookup_prefix 同邏輯但不查 DB）。
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    # 使用 token 字串 hash 作為 key（負 hash 取絕對值）
    return abs(hash(token)) % (2**31)


def _is_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS


async def _check_and_record(key: int, limit: int) -> tuple[bool, int]:
    """檢查並記錄一次請求。回傳 (allowed, remaining)。"""
    now = time.monotonic()
    cutoff = now - _WINDOW_SEC
    async with _LOCK:
        window = _WINDOWS.setdefault(key, deque())
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= limit:
            return False, 0
        window.append(now)
        return True, limit - len(window)


def make_rate_limit_middleware(default_limit: int) -> Any:
    """工廠：產出綁定 default_limit 的中介層函式。"""

    async def rate_limit_active_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if _is_exempt(request.url.path):
            return await call_next(request)

        key = _api_key_id_from_request(request)
        if key is None:
            # 未認證請求直接放行給 auth 中介層拒絕
            return await call_next(request)

        allowed, remaining = await _check_and_record(key, default_limit)
        if not allowed:
            from app.core.response import failure
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content=failure("RATE_LIMIT_EXCEEDED", "請求頻率超過上限").model_dump(),
                headers={
                    "X-RateLimit-Limit": str(default_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(_WINDOW_SEC)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(default_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(_WINDOW_SEC))
        return response

    return rate_limit_active_middleware


def reset_for_test() -> None:
    """測試輔助：清空所有 window。"""
    _WINDOWS.clear()
```

- [ ] **Step 2：撰寫 `tests/unit/test_rate_limit.py`**

```python
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.rate_limit_active import make_rate_limit_middleware, reset_for_test


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_for_test()
    yield
    reset_for_test()


def _build_app(limit: int) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(make_rate_limit_middleware(limit))

    @app.get("/api/v1/test")
    def endpoint() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_under_limit_allowed() -> None:
    app = _build_app(limit=5)
    client = TestClient(app)
    headers = {"Authorization": "Bearer t1"}
    for _ in range(5):
        resp = client.get("/api/v1/test", headers=headers)
        assert resp.status_code == 200
        assert "X-RateLimit-Remaining" in resp.headers


def test_over_limit_blocked() -> None:
    app = _build_app(limit=3)
    client = TestClient(app)
    headers = {"Authorization": "Bearer t1"}
    for _ in range(3):
        client.get("/api/v1/test", headers=headers)
    resp = client.get("/api/v1/test", headers=headers)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert resp.headers["X-RateLimit-Limit"] == "3"
    assert resp.headers["X-RateLimit-Remaining"] == "0"


def test_different_tokens_separate_buckets() -> None:
    app = _build_app(limit=2)
    client = TestClient(app)
    for _ in range(2):
        client.get("/api/v1/test", headers={"Authorization": "Bearer t1"})
    # t1 已用完
    resp1 = client.get("/api/v1/test", headers={"Authorization": "Bearer t1"})
    assert resp1.status_code == 429
    # t2 仍可用
    resp2 = client.get("/api/v1/test", headers={"Authorization": "Bearer t2"})
    assert resp2.status_code == 200


def test_exempt_paths_not_limited() -> None:
    app = _build_app(limit=2)
    client = TestClient(app)
    headers = {"Authorization": "Bearer t1"}
    # /health 不限流（即使超出 limit）
    for _ in range(10):
        resp = client.get("/health", headers=headers)
        assert resp.status_code == 200


def test_unauthenticated_request_passes_through() -> None:
    app = _build_app(limit=2)
    client = TestClient(app)
    # 無 Authorization header，中介層直接放行（後續 auth 中介層處理）
    resp = client.get("/api/v1/test")
    assert resp.status_code == 200
```

- [ ] **Step 3：執行測試 + ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_rate_limit.py -v
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：5 PASS、全綠。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/middleware/rate_limit_active.py backend/tests/unit/test_rate_limit.py
git commit -m "$(@'
feat(m11): Sliding Window 限流（active middleware）

- middleware/rate_limit_active.py：
  - 內存 dict[token_hash, deque[timestamp]] + asyncio.Lock
  - _WINDOW_SEC = 60 秒固定 window
  - make_rate_limit_middleware(default_limit) 工廠回傳綁定 limit 的中介層
  - 豁免路徑：/health / /readiness / /metrics
  - 未認證請求放行給 auth 中介層處理
  - 429 回應含 X-RateLimit-Limit / Remaining / Reset headers
  - reset_for_test 測試輔助
- 5 個單元測試：under limit / over limit / 不同 token 隔離 / exempt path / 未認證放行

Phase 3 改 Redis 後可橫向擴展。

對應計劃：M11 Task 11.3
對應規格：v1.9 §19.4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 11.4：安全標頭 middleware

**Files:**
- Create: `backend/app/middleware/security_headers.py`
- Create: `backend/tests/unit/test_security_headers.py`

- [ ] **Step 1：撰寫 `app/middleware/security_headers.py`**

```python
"""安全標頭注入（規格 §19.6 / §25）。"""

from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint


def make_security_headers_middleware(
    csp_policy: str,
    hsts_max_age: int,
    enabled: bool = True,
) -> Callable:  # type: ignore[type-arg]
    async def security_headers_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if not enabled:
            return response
        response.headers["Content-Security-Policy"] = csp_policy
        response.headers["Strict-Transport-Security"] = f"max-age={hsts_max_age}; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

    return security_headers_middleware
```

- [ ] **Step 2：撰寫 `tests/unit/test_security_headers.py`**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers import make_security_headers_middleware


def _build_app(enabled: bool = True) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(make_security_headers_middleware(
        csp_policy="default-src 'self'",
        hsts_max_age=31536000,
        enabled=enabled,
    ))

    @app.get("/test")
    def endpoint() -> dict[str, str]:
        return {"ok": "yes"}

    return app


def test_headers_injected() -> None:
    client = TestClient(_build_app(enabled=True))
    resp = client.get("/test")
    assert resp.headers["Content-Security-Policy"] == "default-src 'self'"
    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation" in resp.headers["Permissions-Policy"]


def test_disabled_no_headers() -> None:
    client = TestClient(_build_app(enabled=False))
    resp = client.get("/test")
    assert "Content-Security-Policy" not in resp.headers
    assert "Strict-Transport-Security" not in resp.headers
```

- [ ] **Step 3：執行測試 + ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_security_headers.py -v
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：2 PASS、全綠。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/middleware/security_headers.py backend/tests/unit/test_security_headers.py
git commit -m "$(@'
feat(m11): 安全標頭 middleware

- middleware/security_headers.py：
  - 注入 6 個安全 headers：
    - Content-Security-Policy（自 CSP_POLICY ENV）
    - Strict-Transport-Security（max-age + includeSubDomains）
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: geolocation=(), microphone=(), camera=()
  - enabled flag 可由 SECURITY_HEADERS_ENABLED 控制
- 2 個單元測試：注入 / 停用時無

對應計劃：M11 Task 11.4
對應規格：v1.9 §19.6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 11.5：Auth Admin router（軟刪除 + erase）

**Files:**
- Create: `backend/app/routers/auth_admin.py`
- Create: `backend/tests/integration/test_auth_admin.py`

- [ ] **Step 1：撰寫 `app/routers/auth_admin.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.schemas.common import ResponseEnvelope
from app.services.audit import record_audit_event

router = APIRouter(prefix="/api/v1/auth", tags=["auth-admin"])


@router.delete(
    "/keys/{key_id}",
    response_model=ResponseEnvelope[None],
    status_code=status.HTTP_200_OK,
)
def soft_delete_key(
    key_id: int,
    api_key: ApiKey = Depends(require_scope("admin")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[None]:
    """軟刪除：標記 deleted_at（規格 §3.3.10 強制規範 17）。"""
    target = db.get(ApiKey, key_id)
    if target is None or target.deleted_at is not None:
        raise NotFoundError(details={"key_id": key_id})

    target.deleted_at = datetime.now(timezone.utc)
    target.is_active = False
    db.flush()

    record_audit_event(
        db,
        "auth.key_soft_deleted",
        api_key_id=api_key.id,
        target_api_key_id=key_id,
    )
    db.commit()
    return success(None)


@router.delete(
    "/keys/{key_id}/erase",
    response_model=ResponseEnvelope[None],
    status_code=status.HTTP_200_OK,
)
def erase_key(
    key_id: int,
    api_key: ApiKey = Depends(require_scope("admin")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[None]:
    """徹底刪除 + 級聯刪除關聯資料（規格 §3.3.10 / §25.4）。

    順序：
    1. 寫入 audit event（在刪除前，避免 FK 失效）
    2. 刪 transcriptions / audio_files / dataset_samples（具 api_key_id 的全部）
    3. 刪 ApiKey
    """
    target = db.get(ApiKey, key_id)
    if target is None:
        raise NotFoundError(details={"key_id": key_id})

    # 1. audit 先寫（用 target_api_key_id，避免 FK ON DELETE 失效）
    record_audit_event(
        db,
        "auth.key_erased",
        api_key_id=api_key.id,
        target_api_key_id=key_id,
        metadata={"target_name": target.name},
    )
    db.flush()

    # 2. 刪所有引用此 api_key_id 的租戶資料
    for tbl in [
        "dataset_samples",  # 透過 dataset → audio_file 連動
        "youtube_downloads",
        "correction_segments",  # session FK CASCADE 會處理
        "correction_sessions",
        "transcriptions",
        "audio_files",
        "hotwords",  # group FK CASCADE 處理
        "hotword_groups",
        "datasets",
        "finetune_checkpoints",
        "finetune_tasks",
    ]:
        if tbl in ("hotwords", "correction_segments"):
            continue  # 由父表 CASCADE 處理
        db.execute(text(f"DELETE FROM {tbl} WHERE api_key_id = :a"), {"a": key_id})

    # 3. 刪 audit_logs 中以此 key 為 api_key_id 的紀錄
    #    （但保留 target_api_key_id = key_id 的 audit 以保歷史軌跡）
    db.execute(text("DELETE FROM audit_logs WHERE api_key_id = :a AND target_api_key_id IS NULL"), {"a": key_id})

    # 4. 刪 ApiKey 本身
    db.delete(target)
    db.commit()
    return success(None)
```

- [ ] **Step 2：撰寫 `tests/integration/test_auth_admin.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.auth_admin import router as auth_admin_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_admin_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def admin_app(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, str, int]:
    monkeypatch.setenv("API_KEY", "admin-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    db_session.execute(text("TRUNCATE api_keys, audit_logs CASCADE"))

    admin_token = "admin-tok"
    hmac_key = derive_hmac_key("admin-test")
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'admin', '{admin}')"
        ),
        {"h": hash_token(admin_token), "p": lookup_prefix(admin_token, hmac_key)},
    )
    # 建一個目標 key
    target_token = "victim-tok"
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'victim', '{asr:read}')"
        ),
        {"h": hash_token(target_token), "p": lookup_prefix(target_token, hmac_key)},
    )
    target_id = int(db_session.execute(text("SELECT id FROM api_keys WHERE name = 'victim'")).scalar_one())
    db_session.commit()

    return _build_app(db_session), admin_token, target_id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_soft_delete_marks_deleted_at(admin_app, db_session: Session) -> None:
    app, token, target_id = admin_app
    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/auth/keys/{target_id}", headers=_headers(token))
    assert resp.status_code == 200
    row = db_session.execute(
        text("SELECT deleted_at, is_active FROM api_keys WHERE id = :i"), {"i": target_id}
    ).first()
    assert row is not None
    assert row[0] is not None
    assert row[1] is False
    audit = db_session.execute(
        text("SELECT event_type FROM audit_logs WHERE target_api_key_id = :t"), {"t": target_id}
    ).scalar_one()
    assert audit == "auth.key_soft_deleted"


def test_erase_removes_row(admin_app, db_session: Session) -> None:
    app, token, target_id = admin_app
    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/auth/keys/{target_id}/erase", headers=_headers(token))
    assert resp.status_code == 200
    row = db_session.execute(
        text("SELECT id FROM api_keys WHERE id = :i"), {"i": target_id}
    ).first()
    assert row is None
    audit = db_session.execute(
        text("SELECT event_type, metadata FROM audit_logs WHERE target_api_key_id = :t"),
        {"t": target_id},
    ).first()
    assert audit is not None
    assert audit[0] == "auth.key_erased"
    assert audit[1]["target_name"] == "victim"


def test_delete_nonexistent_returns_404(admin_app) -> None:
    app, token, _ = admin_app
    with TestClient(app) as client:
        resp = client.delete("/api/v1/auth/keys/99999", headers=_headers(token))
    assert resp.status_code == 404


def test_soft_delete_requires_admin_scope(admin_app, db_session: Session) -> None:
    app, _, target_id = admin_app
    # 用 victim 的 token（scope=asr:read）
    raw_token = "victim-tok"
    with TestClient(app) as client:
        resp = client.delete(f"/api/v1/auth/keys/{target_id}", headers=_headers(raw_token))
    assert resp.status_code == 403
```

- [ ] **Step 3：執行測試 + ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_auth_admin.py -v
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：4 PASS、全綠。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/routers/auth_admin.py backend/tests/integration/test_auth_admin.py
git commit -m "$(@'
feat(m11): Auth Admin router（軟刪除 + erase）

- routers/auth_admin.py：
  - DELETE /api/v1/auth/keys/:id（軟刪除）
    - 標記 deleted_at + is_active=false
    - 寫 auth.key_soft_deleted audit event
  - DELETE /api/v1/auth/keys/:id/erase（徹底刪除）
    - audit event 先寫（在 FK 失效前）
    - 級聯刪除：transcriptions / audio_files / datasets / dataset_samples /
      hotword_groups / hotwords / youtube_downloads / correction_sessions /
      correction_segments / finetune_tasks / finetune_checkpoints
    - 刪除以此 key 為 api_key_id 的 audit_logs（保留 target_api_key_id 軌跡）
    - 最後刪 ApiKey 本身
  - 兩端點皆 require_scope("admin")
- 4 個整合測試：soft delete / erase / 不存在 404 / 非 admin 403

對應計劃：M11 Task 11.5
對應規格：v1.9 §3.3.10 + §25.4 + 強制規範 17

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 11.6：main.py 整合 + custom docs + M11 整合驗收

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_metrics_endpoint.py`

- [ ] **Step 1：修改 `app/main.py`**

讀取 main.py，做以下整合：

1. import 新 active middleware 與 router：

```python
from app.middleware.prometheus_active import prometheus_active_middleware
from app.middleware.rate_limit_active import make_rate_limit_middleware
from app.middleware.security_headers import make_security_headers_middleware
from app.middleware.tracing_active import configure_tracing, tracing_active_middleware
from app.routers.auth_admin import router as auth_admin_router
from app.routers.metrics import router as metrics_router
```

2. 在 lifespan 內補 tracing 初始化（在 vLLM init 之後）：

```python
        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            configure_tracing(settings.OTEL_EXPORTER_OTLP_ENDPOINT)
```

3. middleware 註冊改為條件式（取代 M2 no-op 註冊段）：

```python
    # M11 active vs M2 no-op 條件式切換
    if settings.PROMETHEUS_ENABLED:
        app.middleware("http")(prometheus_active_middleware)
    else:
        app.middleware("http")(prometheus_middleware)  # M2 no-op

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        app.middleware("http")(tracing_active_middleware)
    else:
        app.middleware("http")(tracing_middleware)  # M2 no-op

    # 限流（active 版本）
    app.middleware("http")(make_rate_limit_middleware(settings.RATE_LIMIT_DEFAULT_PER_MIN))

    # M2 既有 idempotency_middleware（no-op，Phase 3 啟用）
    app.middleware("http")(idempotency_middleware)

    # 安全標頭（最外層，保證所有回應都含）
    if settings.SECURITY_HEADERS_ENABLED:
        app.middleware("http")(make_security_headers_middleware(
            csp_policy=settings.CSP_POLICY,
            hsts_max_age=settings.HSTS_MAX_AGE,
            enabled=True,
        ))

    # M2 既有
    app.middleware("http")(request_id_middleware)
```

4. include 兩個新 router（兩 profile 都啟用）：

```python
    app.include_router(metrics_router)
    app.include_router(auth_admin_router)
```

5. **OPENAPI docs 強制 admin scope 保護**（規格 §21.6）：

把 `app = FastAPI(...)` 的 `docs_url` 改為 None，並補手動 endpoint：

```python
from fastapi.openapi.docs import get_swagger_ui_html

app = FastAPI(
    title="Qwen3-ASR API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.get("/docs", include_in_schema=False)
async def custom_docs(
    api_key: ApiKey = Depends(require_scope("admin")) if settings.OPENAPI_DOCS_REQUIRE_AUTH else None,
):  # type: ignore[no-untyped-def]
    if not settings.OPENAPI_DOCS_ENABLED:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(message="OpenAPI docs disabled")
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Qwen3-ASR API")
```

注意：FastAPI 的 `Depends` 不接受條件式 `None`，需要寫成兩個獨立的 handler 或 always-require 並依 ENV 改 `require_scope("admin")` vs `require_scope("asr:read")`。**最簡作法**：production 強制 admin，dev 允許 read。

或寫成：

```python
def _docs_dep():  # type: ignore[no-untyped-def]
    if settings.OPENAPI_DOCS_REQUIRE_AUTH:
        return Depends(require_scope("admin"))
    return None

# 不在裝飾器層加 dep，改在函式內檢查（不 idiomatic 但簡單）
```

實際採法：M2 既有 `startup_checks` 已強制 production 必須 `OPENAPI_DOCS_REQUIRE_AUTH=true`。所以在 production 永遠 require_scope("admin")：

```python
@app.get("/docs", include_in_schema=False)
async def custom_docs(
    api_key: ApiKey = Depends(require_scope("admin")),
):
    if not settings.OPENAPI_DOCS_ENABLED:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(message="OpenAPI docs disabled")
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Qwen3-ASR API")
```

dev 開發時可在 `.env` 設 `OPENAPI_DOCS_REQUIRE_AUTH=false` 但 `/docs` 仍要求 admin — 與規格 §21.6 一致（嚴格保護）。

- [ ] **Step 2：撰寫 `tests/integration/test_metrics_endpoint.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.prometheus_active import prometheus_active_middleware
from app.routers.metrics import router as metrics_router


@pytest.fixture
def metrics_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(prometheus_active_middleware)
    app.include_router(metrics_router)

    @app.get("/api/v1/test")
    def endpoint() -> dict[str, str]:
        return {"ok": "yes"}

    return app


def test_metrics_endpoint_returns_prometheus_format(metrics_app) -> None:
    client = TestClient(metrics_app)
    # 先打一個 endpoint 產生 metric
    client.get("/api/v1/test")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    # Counter 的 metric type 標頭應該存在
    assert "# TYPE http_requests_total counter" in body


def test_metrics_counter_increments(metrics_app) -> None:
    client = TestClient(metrics_app)
    for _ in range(3):
        client.get("/api/v1/test")
    resp = client.get("/metrics")
    body = resp.text
    # 應該至少能看到 method="GET",endpoint="/api/v1/test" 對應 count >= 3
    lines = [l for l in body.split("\n") if 'http_requests_total{' in l and '/api/v1/test' in l]
    assert any(int(float(l.rsplit(" ", 1)[1])) >= 3 for l in lines)
```

- [ ] **Step 3：執行測試 + 全套**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_metrics_endpoint.py -v
.\.venv\Scripts\pytest.exe -v --cov=app --cov-fail-under=70 --no-header -q 2>&1 | tail -20
```

預期：metrics 2 PASS；全套累積 ~245 個 PASS。

- [ ] **Step 4：docker compose 整合驗收**

```powershell
cd D:\Qwen_asr
@"
API_KEY=m11-token
DB_PASSWORD=m11-db
THIRD_PARTY_LICENSE_ACK=true
DEPLOYMENT_PROFILE=vendor
PROMETHEUS_ENABLED=true
SECURITY_HEADERS_ENABLED=true
"@ | Out-File -Encoding utf8 .env -NoNewline

docker compose up -d postgres
Start-Sleep -Seconds 20
cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:m11-db@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
cd ..
docker compose up -d asr-backend
Start-Sleep -Seconds 30

# 驗證 /metrics
Invoke-WebRequest -Uri "http://localhost:8000/metrics" -UseBasicParsing | Select-Object -ExpandProperty Content | Select-String "http_requests_total"

# 驗證安全 headers
$resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
$resp.Headers["Content-Security-Policy"]
$resp.Headers["X-Frame-Options"]

docker compose down -v
Remove-Item .env
```

預期：
- `/metrics` 含 `http_requests_total`
- `/health` 回應含 CSP + X-Frame-Options: DENY

- [ ] **Step 5：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/main.py backend/tests/integration/test_metrics_endpoint.py
git commit -m "$(@'
feat(m11): main.py 整合 active middleware + custom /docs + metrics 端到端

main.py 變動：
- import 4 個 active middleware + 2 個新 router
- lifespan 補 configure_tracing（若 OTEL_EXPORTER_OTLP_ENDPOINT 設定）
- middleware 註冊改為條件式：
  - PROMETHEUS_ENABLED → active；否則 M2 no-op
  - OTEL_EXPORTER_OTLP_ENDPOINT → active；否則 M2 no-op
  - rate_limit_active 永遠啟用
  - security_headers 依 SECURITY_HEADERS_ENABLED
- docs_url=None + 手動 /docs endpoint（require_scope admin）
- include metrics_router + auth_admin_router

2 個整合測試：/metrics 端點格式 + counter 累加

驗收：
- pytest 累積 ~245 PASS
- docker compose 啟動含 PROMETHEUS_ENABLED=true
- /metrics 暴露 prometheus 格式
- /health 含 6 個安全 headers

對應計劃：M11 Task 11.6
對應規格：v1.9 §21.6 + §22

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Self-Review

**1. Spec coverage（對照設計文件 §3.7 + 規格 §18 / §19 / §21 / §22 / §25）：**

| 設計章節 | 對應 Task |
|---------|----------|
| §3.7 Prometheus middleware 啟用 | T11.2 |
| §3.7 OpenTelemetry tracing | T11.2 |
| §3.7 Sliding Window 限流 | T11.3 |
| §3.7 CSP + 安全標頭 | T11.4 |
| §3.7 OpenAPI 文檔處置 | T11.6（custom /docs） |
| §3.7 軟刪除 + erase | T11.5 |
| §3.7 audit_logs 全面覆蓋 | T11.5（auth.key_* events） |
| §4.7 Prometheus middleware 替換策略 | T11.6 main.py 條件式 |
| §4.8 OPENAPI production 強制 | T11.6 custom_docs require admin |
| §4.9 1 個錯誤碼 | T11.1 |
| §7 ENV 6 個 | T11.1 |

**2. Placeholder scan：** 已搜尋禁用詞，無命中。「Phase 3 改 Redis 後可橫向擴展」「Phase 3 啟用」屬延伸點宣告，非 placeholder。

**3. Type consistency：**
- `make_rate_limit_middleware(limit)` 工廠回傳 `middleware` 函式，main.py 與 test 使用一致
- `make_security_headers_middleware(csp_policy, hsts_max_age, enabled)` 三個 keyword args 在 main.py 與 test 對齊
- `auth.key_soft_deleted` / `auth.key_erased` audit event_type 字串在 router 與 test assertion 一致

---

## Execution Handoff

Plan complete: `docs/superpowers/plans/2026-05-16-phase2-m11-observability-security.md`. 6 個 task 約 1500 行。

**Phase 2 全部 7 份 plan 完成**：
1. M5 Hotword + Dataset（1931 行）
2. M6 前端 scaffolding（1452 行）
3. M7 Aligner + Diarization + 後處理 + 糾錯（1826 行）
4. M8 Fine-tune（1472 行）
5. M9 YouTube + 校正工作台（1956 行）
6. M10 WebSocket 質檢（885 行）
7. M11 可觀測性 + 安全控管（~1500 行）

合計 ~11000+ 行 plan，搭配 838 行 design.md，整個 Phase 2 設計與實作藍圖就緒。
