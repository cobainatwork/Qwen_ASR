"""WebSocket 連線管理（規格 §3.3.9，CLAUDE.md mandate 14）。

維護 api_key_id → set[ConnectionState] 對應。
連線數超過上限時拒絕新連線，回 WsMaxConnectionsError。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import ClassVar

import structlog
from fastapi import WebSocket

from app.core.exceptions import WsMaxConnectionsError

logger = structlog.get_logger(__name__)


@dataclass(eq=False)
class ConnectionState:
    websocket: WebSocket
    api_key_id: int
    last_ping_at: float  # asyncio 單調時鐘（秒），由 HeartbeatWatchdog.touch 更新
    watchdog_task: asyncio.Task[None] | None = field(default=None)


class WebSocketManager:
    """類別層級（singleton-style）連線狀態容器。

    所有方法皆為 classmethod；狀態儲存在類別屬性，
    方便跨呼叫方（router / heartbeat）共用，無需注入實例。
    """

    _connections: ClassVar[dict[int, set[ConnectionState]]] = {}
    _lock: ClassVar[asyncio.Lock | None] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Lazy 建立 Lock，確保綁定到當前執行中的 event loop。

        若在 import 時建立（類別屬性直接 = asyncio.Lock()），
        會綁定到 import 時的 loop，造成跨測試的 loop 不一致錯誤。
        """
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def register(
        cls,
        ws: WebSocket,
        api_key_id: int,
        max_per_key: int,
    ) -> ConnectionState:
        """登記新連線；若超出上限則拋 WsMaxConnectionsError。"""
        async with cls._get_lock():
            existing = cls._connections.get(api_key_id, set())
            if len(existing) >= max_per_key:
                raise WsMaxConnectionsError(
                    details={
                        "api_key_id": api_key_id,
                        "current": len(existing),
                        "max": max_per_key,
                    }
                )
            state = ConnectionState(
                websocket=ws,
                api_key_id=api_key_id,
                last_ping_at=asyncio.get_event_loop().time(),
            )
            cls._connections.setdefault(api_key_id, set()).add(state)
            logger.info(
                "ws connection registered",
                api_key_id=api_key_id,
                total=len(cls._connections[api_key_id]),
                max_per_key=max_per_key,
            )
            return state

    @classmethod
    async def unregister(cls, state: ConnectionState) -> None:
        """移除連線並取消心跳 watchdog task（若存在）。"""
        async with cls._get_lock():
            connections = cls._connections.get(state.api_key_id)
            if connections is not None:
                connections.discard(state)
                if not connections:
                    cls._connections.pop(state.api_key_id, None)
            if state.watchdog_task is not None and not state.watchdog_task.done():
                state.watchdog_task.cancel()
        logger.info(
            "ws connection unregistered",
            api_key_id=state.api_key_id,
        )

    @classmethod
    def count_for_key(cls, api_key_id: int) -> int:
        """回傳指定 api_key_id 目前的連線數（不取鎖，唯讀快照）。"""
        return len(cls._connections.get(api_key_id, set()))

    @classmethod
    async def reset_for_test(cls) -> None:
        """清除所有類別狀態，供測試夾具使用。

        不取鎖（避免 event loop 已結束的 teardown 死鎖）；
        直接清空 _connections 並重置 _lock。
        """
        cls._connections.clear()
        cls._lock = None
