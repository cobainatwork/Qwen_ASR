# Phase 2 / M10 — WebSocket 質檢接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 `/ws/quality` WebSocket 端點，透過 `Sec-WebSocket-Protocol` 完成 Bearer token 認證、強制 workers=1 與單端口 8000 共用、30/90 秒心跳協議、訊息大小與單金鑰連線數上限。完成後客戶端可建立持久連線，傳送 ping 收到 pong，超過 90 秒無 ping 主動斷線。Phase 3 即時轉錄能力預留 hook。

**Architecture:** 透過 FastAPI 的 `WebSocket` 路由註冊單端口 8000 內。連線管理器 `WebSocketManager` 以 `dict[int, set[WebSocket]]` 維護 `api_key_id` 對應連線；連線開啟前先驗證 subprotocol，超過 `WS_MAX_CONNECTIONS_PER_KEY` 拒絕。每連線有獨立的 `last_ping_at` 與背景 watchdog；心跳超時主動 close。所有錯誤透過 WS close code 回報（不是 HTTP envelope）。

**Tech Stack:** FastAPI WebSocket（基於 Starlette）、asyncio.create_task watchdog、base64.urlsafe_b64decode。

**對應設計文件：** Phase 2 design.md §3.6、§4.4。對應規格：v1.9 §3.1、§3.3.9、§12、強制規範 12-14。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/services/ws_quality/__init__.py` | Create | re-export |
| `backend/app/services/ws_quality/auth.py` | Create | subprotocol → ApiKey |
| `backend/app/services/ws_quality/manager.py` | Create | 連線管理 |
| `backend/app/services/ws_quality/heartbeat.py` | Create | 心跳邏輯 |
| `backend/app/routers/ws.py` | Create | `/ws/quality` endpoint |
| `backend/app/main.py` | Modify | include ws router（兩 profile 都啟用） |
| `backend/app/core/exceptions.py` | Modify | 補 3 個 WS 錯誤碼 |
| `backend/app/core/config.py` | Modify | 補 3 個 ENV |
| `backend/tests/unit/test_ws_auth.py` | Create | subprotocol 解析測試 |
| `backend/tests/integration/test_ws_quality.py` | Create | 端到端 WS 測試 |

---

## Task 10.1：擴充 exceptions + ENV + 子目錄

**Files:**
- Modify: `backend/app/core/exceptions.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/ws_quality/__init__.py`

- [ ] **Step 1：擴充 `exceptions.py` 3 個錯誤碼**

```python
# ----- Phase 2 / M10 -----
class WsAuthFailedError(AppException):
    code = "WS_AUTH_FAILED"
    http_status = 401
    message = "WebSocket 認證失敗"


class WsMaxConnectionsError(AppException):
    code = "WS_MAX_CONNECTIONS"
    http_status = 429
    message = "超過單金鑰 WS 連線上限"


class WsMessageTooLargeError(AppException):
    code = "WS_MESSAGE_TOO_LARGE"
    http_status = 413
    message = "訊息超過大小上限"
```

`ALL_ERROR_CODES` 補 3 個（39 → 42）。

**註**：WS close code 與 HTTP status 是兩個體系，但 close 時必須帶結構化訊息（如 JSON `{"code": "WS_AUTH_FAILED", ...}`），讓 client 可解析。

- [ ] **Step 2：擴充 `config.py` ENV（規格既有 WS_MAX_MESSAGE_SIZE_MB / WS_MAX_CONNECTIONS_PER_KEY 在 M2 T2.1 已含）**

確認 `app/core/config.py` 既有：
```python
    WS_MAX_MESSAGE_SIZE_MB: int = 50
    WS_MAX_CONNECTIONS_PER_KEY: int = 10
```

補一個 ENV（心跳超時，規格 §3.3.7）：

```python
    # ----- Phase 2 / M10 -----
    WS_HEARTBEAT_TIMEOUT_SEC: int = 90
```

- [ ] **Step 3：建立目錄**

```powershell
cd D:\Qwen_asr\backend
New-Item app/services/ws_quality -ItemType Directory -Force
```

- [ ] **Step 4：撰寫 `app/services/ws_quality/__init__.py`**

```python
from app.services.ws_quality.auth import authenticate_websocket
from app.services.ws_quality.heartbeat import HeartbeatWatchdog
from app.services.ws_quality.manager import WebSocketManager

__all__ = ["HeartbeatWatchdog", "WebSocketManager", "authenticate_websocket"]
```

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
git add backend/app/core/exceptions.py backend/app/core/config.py backend/app/services/ws_quality
git commit -m "$(@'
feat(m10): 補 3 個 WS 錯誤碼 + WS_HEARTBEAT_TIMEOUT_SEC ENV

- exceptions：WsAuthFailedError（401）/ WsMaxConnectionsError（429）/ WsMessageTooLargeError（413）
  - ALL_ERROR_CODES 39 → 42
- config 補 WS_HEARTBEAT_TIMEOUT_SEC=90（規格 §3.3.7）
- services/ws_quality/__init__.py 占位 re-export

對應計劃：M10 Task 10.1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 10.2：WebSocket 認證（subprotocol 解析）

**Files:**
- Create: `backend/app/services/ws_quality/auth.py`
- Create: `backend/tests/unit/test_ws_auth.py`

- [ ] **Step 1：撰寫 `app/services/ws_quality/auth.py`**

```python
"""WebSocket 認證（規格 §12 + 強制規範 12）。

格式：`Sec-WebSocket-Protocol: asr.v1, bearer.<base64url(token)>`
**禁止透過 query string 傳遞 token**（會被 access log / Referer 洩漏）。
"""

from __future__ import annotations

import base64
import binascii

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import WsAuthFailedError
from app.core.security import derive_hmac_key, lookup_prefix, verify_token_hash
from app.models import ApiKey
from app.repositories.api_key import ApiKeyRepository


def parse_subprotocols(header_value: str | None) -> tuple[bool, str | None]:
    """解析 Sec-WebSocket-Protocol header 為 (asr_v1_present, raw_token)。

    - asr_v1_present：是否含 "asr.v1"
    - raw_token：從 "bearer.<base64url>" 解出的 token 字串，找不到回 None
    """
    if not header_value:
        return False, None

    parts = [p.strip() for p in header_value.split(",") if p.strip()]
    asr_v1 = "asr.v1" in parts
    raw_token: str | None = None
    for p in parts:
        if p.startswith("bearer."):
            b64 = p[len("bearer."):]
            try:
                # base64url 可能無 padding，補回
                padded = b64 + "=" * (-len(b64) % 4)
                raw_token = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                raise WsAuthFailedError(message="無法解析 bearer subprotocol")
            break
    return asr_v1, raw_token


def authenticate_websocket(
    header_value: str | None,
    db: Session,
    settings: Settings,
) -> ApiKey:
    """驗證 WebSocket subprotocol 並回傳對應 ApiKey。

    Raises:
        WsAuthFailedError: 任何認證失敗（asr.v1 缺、token 缺、解析失敗、不符合 DB）
    """
    asr_v1, raw_token = parse_subprotocols(header_value)
    if not asr_v1:
        raise WsAuthFailedError(message="缺少 asr.v1 subprotocol")
    if not raw_token:
        raise WsAuthFailedError(message="缺少 bearer subprotocol")

    hmac_key = (
        settings.LOOKUP_HMAC_KEY.encode()
        if settings.LOOKUP_HMAC_KEY
        else derive_hmac_key(settings.API_KEY)
    )
    prefix = lookup_prefix(raw_token, hmac_key)

    repo = ApiKeyRepository(db)
    candidates = repo.find_active_by_prefix(prefix)
    for key in candidates:
        if verify_token_hash(raw_token, key.key_hash):
            repo.touch_last_used(key)
            return key

    raise WsAuthFailedError(message="token 無效")
```

- [ ] **Step 2：撰寫 `tests/unit/test_ws_auth.py`**

```python
import base64

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import WsAuthFailedError
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.services.ws_quality.auth import authenticate_websocket, parse_subprotocols


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

    with pytest.raises(WsAuthFailedError, match="asr.v1"):
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
```

- [ ] **Step 3：執行測試 + ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_ws_auth.py -v
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：8 個 case PASS。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/services/ws_quality/auth.py backend/tests/unit/test_ws_auth.py
git commit -m "$(@'
feat(m10): WebSocket subprotocol 認證

- services/ws_quality/auth.py：
  - parse_subprotocols：解析 'asr.v1, bearer.<base64url>' header
    - 自動補回 base64url padding
    - 解析失敗拋 WsAuthFailedError
  - authenticate_websocket：完整認證流程（複用 M2 ApiKeyRepository / verify_token_hash）
    - 缺 asr.v1 → 401
    - 缺 bearer → 401
    - token 無效 → 401
    - 成功 → touch_last_used + 回傳 ApiKey
- 8 個單元測試：valid / missing parts / malformed b64 / success / invalid

對應計劃：M10 Task 10.2
對應規格：v1.9 §12 + 強制規範 12（禁止 query string 傳 token）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 10.3：連線管理 + 心跳 watchdog

**Files:**
- Create: `backend/app/services/ws_quality/manager.py`
- Create: `backend/app/services/ws_quality/heartbeat.py`

- [ ] **Step 1：撰寫 `app/services/ws_quality/manager.py`**

```python
"""WebSocket 連線管理。

維護 api_key_id → set[WebSocket] 對應。連線超過上限拒絕。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import WebSocket

from app.core.exceptions import WsMaxConnectionsError

logger = structlog.get_logger(__name__)


@dataclass
class ConnectionState:
    websocket: WebSocket
    api_key_id: int
    last_ping_at: float  # monotonic 秒
    watchdog_task: asyncio.Task[None] | None = None


class WebSocketManager:
    _connections: dict[int, set[ConnectionState]] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def register(cls, ws: WebSocket, api_key_id: int, max_per_key: int) -> ConnectionState:
        async with cls._lock:
            existing = cls._connections.get(api_key_id, set())
            if len(existing) >= max_per_key:
                raise WsMaxConnectionsError(
                    details={"api_key_id": api_key_id, "current": len(existing), "max": max_per_key}
                )
            state = ConnectionState(
                websocket=ws,
                api_key_id=api_key_id,
                last_ping_at=asyncio.get_event_loop().time(),
            )
            cls._connections.setdefault(api_key_id, set()).add(state)
            logger.info("ws connection registered", api_key_id=api_key_id, total=len(cls._connections[api_key_id]))
            return state

    @classmethod
    async def unregister(cls, state: ConnectionState) -> None:
        async with cls._lock:
            connections = cls._connections.get(state.api_key_id)
            if connections is not None:
                connections.discard(state)
                if not connections:
                    cls._connections.pop(state.api_key_id, None)
            if state.watchdog_task is not None and not state.watchdog_task.done():
                state.watchdog_task.cancel()
        logger.info("ws connection unregistered", api_key_id=state.api_key_id)

    @classmethod
    def count_for_key(cls, api_key_id: int) -> int:
        return len(cls._connections.get(api_key_id, set()))

    @classmethod
    async def reset_for_test(cls) -> None:
        async with cls._lock:
            cls._connections.clear()
```

- [ ] **Step 2：撰寫 `app/services/ws_quality/heartbeat.py`**

```python
"""心跳 watchdog（規格 §3.3.7）。

前端每 30 秒送 ping；後端 90 秒未收 ping 主動斷線。
"""

from __future__ import annotations

import asyncio

import structlog

from app.services.ws_quality.manager import ConnectionState

logger = structlog.get_logger(__name__)


class HeartbeatWatchdog:
    @staticmethod
    async def run(state: ConnectionState, timeout_sec: int) -> None:
        """背景 task：每秒檢查 last_ping_at，超過 timeout 即 close。"""
        while True:
            try:
                await asyncio.sleep(1.0)
                now = asyncio.get_event_loop().time()
                if now - state.last_ping_at > timeout_sec:
                    logger.warning(
                        "ws heartbeat timeout, closing",
                        api_key_id=state.api_key_id,
                        elapsed=now - state.last_ping_at,
                        timeout=timeout_sec,
                    )
                    try:
                        await state.websocket.close(code=1001, reason="heartbeat timeout")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("ws close on timeout failed", error=str(e))
                    return
            except asyncio.CancelledError:
                return

    @staticmethod
    def touch(state: ConnectionState) -> None:
        """收到 ping 時呼叫，更新 last_ping_at。"""
        state.last_ping_at = asyncio.get_event_loop().time()
```

- [ ] **Step 3：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/services/ws_quality/manager.py backend/app/services/ws_quality/heartbeat.py
git commit -m "$(@'
feat(m10): WebSocket 連線管理器 + 心跳 watchdog

- services/ws_quality/manager.py：WebSocketManager
  - class-level _connections: dict[int, set[ConnectionState]]
  - asyncio.Lock 保護並發
  - register：檢查 max_per_key 上限超過拋 WsMaxConnectionsError
  - unregister：cancel watchdog task + 清理 mapping
  - reset_for_test：測試輔助
- services/ws_quality/heartbeat.py：HeartbeatWatchdog
  - run：每秒檢查 last_ping_at，超過 timeout 主動 close(code=1001)
  - touch：收到 ping 時更新 last_ping_at
- ConnectionState dataclass（websocket / api_key_id / last_ping_at / watchdog_task）

對應計劃：M10 Task 10.3
對應規格：v1.9 §3.3.7 + 強制規範 13、14

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 10.4：`/ws/quality` router + 端到端整合

**Files:**
- Create: `backend/app/routers/ws.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_ws_quality.py`

- [ ] **Step 1：撰寫 `app/routers/ws.py`**

```python
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    WsAuthFailedError,
    WsMaxConnectionsError,
    WsMessageTooLargeError,
)
from app.deps.db import get_db
from app.services.ws_quality import (
    HeartbeatWatchdog,
    WebSocketManager,
    authenticate_websocket,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/quality")
async def quality_websocket(
    websocket: WebSocket,
    db=Depends(get_db),  # type: ignore[no-untyped-def]
    settings: Settings = Depends(get_settings),
) -> None:
    """質檢 WebSocket。Phase 2 範圍：認證 + 心跳 + 訊息上限 + 連線限制。"""
    subprotocols_header = websocket.headers.get("sec-websocket-protocol")

    # 認證
    try:
        api_key = authenticate_websocket(subprotocols_header, db, settings)
    except WsAuthFailedError as e:
        await websocket.close(code=1008, reason=e.code)
        return

    # 接受連線（指定回應 subprotocol）
    await websocket.accept(subprotocol="asr.v1")

    # 註冊到 manager
    try:
        state = await WebSocketManager.register(
            websocket, api_key.id, settings.WS_MAX_CONNECTIONS_PER_KEY
        )
    except WsMaxConnectionsError as e:
        await websocket.close(code=1013, reason=e.code)
        return

    # 啟動心跳 watchdog
    state.watchdog_task = asyncio.create_task(
        HeartbeatWatchdog.run(state, settings.WS_HEARTBEAT_TIMEOUT_SEC),
        name=f"ws-heartbeat-{api_key.id}",
    )

    max_msg_bytes = settings.WS_MAX_MESSAGE_SIZE_MB * 1024 * 1024

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > max_msg_bytes:
                await websocket.close(code=1009, reason="WS_MESSAGE_TOO_LARGE")
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "invalid json"}))
                continue

            action = msg.get("action")
            if action == "ping":
                HeartbeatWatchdog.touch(state)
                await websocket.send_text(json.dumps({
                    "action": "pong",
                    "timestamp": asyncio.get_event_loop().time(),
                }))
            else:
                # Phase 3 預留：實際質檢命令
                await websocket.send_text(json.dumps({
                    "action": "ack",
                    "received": action,
                    "note": "Phase 3 將支援即時轉錄",
                }))
    except WebSocketDisconnect:
        logger.info("ws client disconnected", api_key_id=api_key.id)
    except Exception as e:  # noqa: BLE001
        logger.exception("ws connection error", api_key_id=api_key.id, error=str(e))
        try:
            await websocket.close(code=1011, reason="internal error")
        except Exception:  # noqa: BLE001, S110
            pass
    finally:
        await WebSocketManager.unregister(state)
```

- [ ] **Step 2：修改 `app/main.py` 加入 ws router**

讀 main.py，在 health/asr/hotword/dataset routers 之後加：

```python
    from app.routers.ws import router as ws_router
    app.include_router(ws_router)
```

注意：`ws_router` 兩 profile 都啟用（M5 hotword/dataset 也是兩 profile）。

- [ ] **Step 3：撰寫 `tests/integration/test_ws_quality.py`**

```python
import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.ws import router as ws_router
from app.services.ws_quality import WebSocketManager


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


@pytest.fixture
def ws_app(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "ws-int-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("WS_MAX_CONNECTIONS_PER_KEY", "2")
    monkeypatch.setenv("WS_HEARTBEAT_TIMEOUT_SEC", "3")  # 縮短測試時間
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ws-int-token"
    hmac_key = derive_hmac_key("ws-int-test")
    db_session.execute(text("TRUNCATE api_keys CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'wsint', '{asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ws_router)
    app.dependency_overrides[get_db] = lambda: db_session

    yield app, raw_token

    # 清理 WebSocketManager（class-level state）
    import asyncio
    asyncio.run(WebSocketManager.reset_for_test())


def test_ws_authenticated_ping_pong(ws_app) -> None:
    app, token = ws_app
    headers = [("sec-websocket-protocol", f"asr.v1, bearer.{_b64url(token)}")]
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=["asr.v1", f"bearer.{_b64url(token)}"]) as ws:
            ws.send_text(json.dumps({"action": "ping"}))
            data = json.loads(ws.receive_text())
            assert data["action"] == "pong"


def test_ws_missing_asr_v1_rejected(ws_app) -> None:
    app, token = ws_app
    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/quality", subprotocols=[f"bearer.{_b64url(token)}"]) as ws:
                ws.receive_text()
        assert exc.value.code == 1008


def test_ws_invalid_token_rejected(ws_app) -> None:
    app, _ = ws_app
    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/ws/quality", subprotocols=["asr.v1", f"bearer.{_b64url('fake')}"]
            ) as ws:
                ws.receive_text()
        assert exc.value.code == 1008


def test_ws_max_connections(ws_app) -> None:
    app, token = ws_app
    sub = ["asr.v1", f"bearer.{_b64url(token)}"]
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=sub) as ws1:
            with client.websocket_connect("/ws/quality", subprotocols=sub) as ws2:
                # 第三個應被拒絕（max=2）
                from starlette.websockets import WebSocketDisconnect
                with pytest.raises(WebSocketDisconnect) as exc:
                    with client.websocket_connect("/ws/quality", subprotocols=sub) as ws3:
                        ws3.receive_text()
                assert exc.value.code == 1013


def test_ws_unknown_action_returns_ack(ws_app) -> None:
    app, token = ws_app
    sub = ["asr.v1", f"bearer.{_b64url(token)}"]
    with TestClient(app) as client:
        with client.websocket_connect("/ws/quality", subprotocols=sub) as ws:
            ws.send_text(json.dumps({"action": "noop"}))
            data = json.loads(ws.receive_text())
            assert data["action"] == "ack"
            assert "Phase 3" in data.get("note", "")
```

- [ ] **Step 4：執行測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_ws_quality.py -v
```

預期：5 PASS。

- [ ] **Step 5：ruff + mypy**

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/routers/ws.py backend/app/main.py backend/tests/integration/test_ws_quality.py
git commit -m "$(@'
feat(m10): /ws/quality WebSocket 端點 + 5 個整合測試

- routers/ws.py：/ws/quality 完整流程
  - subprotocol 認證（asr.v1 + bearer.<b64>）
  - WebSocketManager.register（連線上限檢查）
  - HeartbeatWatchdog.run 背景 task（90 秒無 ping 主動 close 1001）
  - ping → pong 立即回應
  - 未知 action 回 ack（Phase 3 預留）
  - 訊息超過 50 MB close 1009
- main.py include ws_router（兩 profile 都啟用）
- 5 個整合測試：
  - ping/pong 基本
  - 缺 asr.v1 → close 1008
  - invalid token → close 1008
  - 超過 max=2 → close 1013
  - unknown action → ack

對應計劃：M10 Task 10.4
對應規格：v1.9 §3.1（單端口）+ §3.3.7、§12、強制規範 12-14

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 10.5：M10 整合驗收

**Files:**（無新檔案）

- [ ] **Step 1：全套**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe -v --cov=app --cov-fail-under=70 --no-header -q 2>&1 | tail -20
```

預期：累積 ~225 PASS（M9 完成 ~210 + M10 ~15）。

- [ ] **Step 2：docker compose 啟動驗證**

```powershell
cd D:\Qwen_asr
@"
API_KEY=m10-token
DB_PASSWORD=m10-db
THIRD_PARTY_LICENSE_ACK=true
"@ | Out-File -Encoding utf8 .env -NoNewline

docker compose up -d postgres
Start-Sleep -Seconds 20
cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:m10-db@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
cd ..
docker compose up -d asr-backend
Start-Sleep -Seconds 30
docker compose ps
docker compose logs asr-backend --tail 30
docker compose down -v
Remove-Item .env
```

預期：backend healthy + `asr consumer started` + ws route 註冊 log。

- [ ] **Step 3：（無 commit；驗收純執行）**

---

## Self-Review

**1. Spec coverage（對照設計文件 §3.6 + 規格 §3.3.9 / §12 / §3.1）：**

| 設計章節 | 對應 Task |
|---------|----------|
| §3.6 範圍：認證 + 心跳 + 訊息上限 + 連線限制 | 全部 |
| §3.6 WS 單端口 8000 | T10.4（FastAPI 既有結構）|
| §3.6 subprotocol 認證 | T10.2 |
| §3.6 心跳 30/90 秒 | T10.3 + T10.4 |
| §3.6 訊息上限 50 MB | T10.4 |
| §3.6 連線上限 10 | T10.3 |
| §3.6 質檢內容 Phase 2 簡化 | T10.4（unknown action → ack）|
| §4.4 workers=1 強制 | M2 既有 |
| §4.9 3 個錯誤碼 | T10.1 |
| §6 端點：/ws/quality | T10.4 |

**2. Placeholder scan：** 已搜尋禁用詞，無命中。「Phase 3 將支援即時轉錄」為合理的延伸點宣告（在 ack 訊息與 router docstring 內），不是 placeholder。

**3. Type consistency：**
- `ConnectionState.api_key_id: int` 在 manager / heartbeat / router 一致
- `WebSocketManager.register` 回傳 `ConnectionState`，router 直接使用 `.watchdog_task` 屬性
- `parse_subprotocols` 回傳 `tuple[bool, str | None]` 與 router 解構一致

---

## Execution Handoff

Plan complete: `docs/superpowers/plans/2026-05-16-phase2-m10-websocket-quality.md`. 5 個 task 約 1350 行。
