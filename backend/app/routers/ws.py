"""WebSocket /ws/quality — Phase 2 質檢端點。

範圍：認證（subprotocol）+ 連線管理 + 心跳 watchdog + 訊息上限 + Phase 3 streaming 預留 hook。

完整流程：
1. 解析 Sec-WebSocket-Protocol → authenticate_websocket → ApiKey。
2. 檢查 asr:write scope（規格 §3.3.7 + §19.1.1）。
3. accept(subprotocol="asr.v1")。
4. WebSocketManager.register（檢查 per-key 連線上限）。
5. 發送 {"action": "connected", "connection_id": <uuid4>}。
6. 啟動 HeartbeatWatchdog 背景 task（settings.WS_HEARTBEAT_TIMEOUT_SEC）。
7. 訊息迴圈：
   - len(raw) > WS_MAX_MESSAGE_SIZE_MB → close(1009, "WS_MESSAGE_TOO_LARGE")。
   - action="ping" → touch + 回 pong。
   - action="stream.start" → 回 stream.unavailable + Phase 3 限制清單。
   - else → 回 ack（Phase 3 將擴充）。
8. 任何 disconnect / exception → unregister（cancel watchdog）。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import WsAuthFailedError, WsMaxConnectionsError
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
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    subprotocols_header = websocket.headers.get("sec-websocket-protocol")

    # 認證：解析 subprotocol header，驗證 bearer token
    try:
        api_key = authenticate_websocket(subprotocols_header, db, settings)
    except WsAuthFailedError as e:
        await websocket.close(code=1008, reason=e.code)
        return

    # Scope 檢查（規格 §3.3.7 + §19.1.1）
    scopes: list[str] = list(api_key.scopes) if api_key.scopes else []
    if "asr:write" not in scopes:
        logger.warning(
            "ws scope check failed",
            api_key_id=api_key.id,
            required="asr:write",
            actual=scopes,
        )
        await websocket.close(code=1008, reason="AUTH_INSUFFICIENT_SCOPE")
        return

    # Subprotocol 在 accept 中回應，client 才會確認協商成功
    await websocket.accept(subprotocol="asr.v1")

    # 登記連線；超出 per-key 上限時拒絕
    try:
        state = await WebSocketManager.register(
            websocket, api_key.id, settings.WS_MAX_CONNECTIONS_PER_KEY
        )
    except WsMaxConnectionsError as e:
        await websocket.close(code=1013, reason=e.code)
        return

    connection_id = str(uuid.uuid4())
    logger.info(
        "ws /ws/quality connected",
        api_key_id=api_key.id,
        connection_id=connection_id,
    )

    # 啟動心跳 watchdog（背景 task，超時 close(1001)）
    state.watchdog_task = asyncio.create_task(
        HeartbeatWatchdog.run(state, settings.WS_HEARTBEAT_TIMEOUT_SEC),
        name=f"ws-heartbeat-{api_key.id}-{connection_id[:8]}",
    )

    # 初始 connected 訊息（規格 §3.3.7）
    await websocket.send_text(
        json.dumps({"action": "connected", "connection_id": connection_id})
    )

    max_msg_bytes = settings.WS_MAX_MESSAGE_SIZE_MB * 1024 * 1024

    try:
        while True:
            raw = await websocket.receive_text()

            if len(raw.encode("utf-8")) > max_msg_bytes:
                logger.warning(
                    "ws message too large",
                    api_key_id=api_key.id,
                    connection_id=connection_id,
                    size_bytes=len(raw.encode("utf-8")),
                )
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
                await websocket.send_text(
                    json.dumps(
                        {
                            "action": "pong",
                            "timestamp": asyncio.get_running_loop().time(),
                        }
                    )
                )
            elif action == "stream.start":
                # Phase 3 hook: T10.6 will replace with get_streaming_limitations()
                await websocket.send_text(
                    json.dumps(
                        {
                            "action": "stream.unavailable",
                            "reason": "streaming endpoint reserved for Phase 3",
                            "limitations": [
                                "qwen-asr 0.0.6 streaming does not support timestamps",
                                "qwen-asr 0.0.6 streaming does not support batch input",
                            ],
                        }
                    )
                )
            else:
                await websocket.send_text(
                    json.dumps(
                        {
                            "action": "ack",
                            "received": action,
                            "note": (
                                "Phase 3 will support live transcription"
                                " and additional QC actions"
                            ),
                        }
                    )
                )
    except WebSocketDisconnect:
        logger.info(
            "ws client disconnected",
            api_key_id=api_key.id,
            connection_id=connection_id,
        )
    except Exception as e:
        logger.exception(
            "ws connection error",
            api_key_id=api_key.id,
            connection_id=connection_id,
            error=str(e),
        )
        try:
            await websocket.close(code=1011, reason="internal error")
        except Exception as close_err:
            logger.warning(
                "ws close on error failed",
                api_key_id=api_key.id,
                connection_id=connection_id,
                error=str(close_err),
            )
    finally:
        await WebSocketManager.unregister(state)
