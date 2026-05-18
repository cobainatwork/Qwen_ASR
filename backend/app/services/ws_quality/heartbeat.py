"""心跳 watchdog（規格 §3.3.7，CLAUDE.md mandate 13）。

前端每 30 秒送 {"action": "ping"}；
後端 90 秒（WS_HEARTBEAT_TIMEOUT_SEC）未收到 ping 主動斷線 code=1001。
"""

from __future__ import annotations

import asyncio

import structlog

from app.services.ws_quality.manager import ConnectionState

logger = structlog.get_logger(__name__)


class HeartbeatWatchdog:
    """靜態方法集合；以 asyncio.Task 形式執行在每條 WS 連線的背景。"""

    @staticmethod
    async def run(state: ConnectionState, timeout_sec: int) -> None:
        """背景 task：每秒檢查 last_ping_at，超過 timeout 即 close(1001)。

        正常結束路徑：
        - 超時 → 呼叫 ws.close(code=1001, reason="heartbeat timeout") 後 return。
        - 被 cancel（連線斷開時由 unregister 呼叫）→ CancelledError 捕捉後 return。
        """
        while True:
            try:
                await asyncio.sleep(1.0)
                now = asyncio.get_running_loop().time()
                elapsed = now - state.last_ping_at
                if elapsed > timeout_sec:
                    logger.warning(
                        "ws heartbeat timeout, closing",
                        api_key_id=state.api_key_id,
                        elapsed=elapsed,
                        timeout=timeout_sec,
                    )
                    try:
                        await state.websocket.close(code=1001, reason="heartbeat timeout")
                    except Exception as exc:
                        logger.warning(
                            "ws close on timeout failed",
                            api_key_id=state.api_key_id,
                            error=str(exc),
                        )
                    return
            except asyncio.CancelledError:
                raise

    @staticmethod
    def touch(state: ConnectionState) -> None:
        """收到 ping 時更新 last_ping_at，重置超時計時器。"""
        state.last_ping_at = asyncio.get_running_loop().time()
