"""Unit tests for WebSocketManager (T10.3).

asyncio_mode = "auto" in pyproject.toml — @pytest.mark.asyncio decorators are
redundant but included for clarity, matching project convention.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from app.core.exceptions import WsMaxConnectionsError
from app.services.ws_quality.manager import WebSocketManager


@pytest.fixture(autouse=True)
async def _reset_manager() -> None:  # type: ignore[misc]
    await WebSocketManager.reset_for_test()
    yield
    await WebSocketManager.reset_for_test()


@pytest.mark.asyncio
async def test_register_under_limit_succeeds() -> None:
    ws = MagicMock()
    state = await WebSocketManager.register(ws, api_key_id=1, max_per_key=3)
    assert state.api_key_id == 1
    assert WebSocketManager.count_for_key(1) == 1


@pytest.mark.asyncio
async def test_register_multiple_under_limit() -> None:
    ws = MagicMock()
    await WebSocketManager.register(ws, api_key_id=1, max_per_key=3)
    await WebSocketManager.register(ws, api_key_id=1, max_per_key=3)
    assert WebSocketManager.count_for_key(1) == 2


@pytest.mark.asyncio
async def test_register_at_limit_raises() -> None:
    ws = MagicMock()
    for _ in range(2):
        await WebSocketManager.register(ws, api_key_id=2, max_per_key=2)
    with pytest.raises(WsMaxConnectionsError):
        await WebSocketManager.register(ws, api_key_id=2, max_per_key=2)


@pytest.mark.asyncio
async def test_count_for_key_returns_zero_when_no_connections() -> None:
    assert WebSocketManager.count_for_key(999) == 0


@pytest.mark.asyncio
async def test_count_for_key_tracks_multiple_keys_independently() -> None:
    ws = MagicMock()
    await WebSocketManager.register(ws, api_key_id=10, max_per_key=5)
    await WebSocketManager.register(ws, api_key_id=10, max_per_key=5)
    await WebSocketManager.register(ws, api_key_id=11, max_per_key=5)
    assert WebSocketManager.count_for_key(10) == 2
    assert WebSocketManager.count_for_key(11) == 1


@pytest.mark.asyncio
async def test_unregister_removes_connection() -> None:
    ws = MagicMock()
    state = await WebSocketManager.register(ws, api_key_id=3, max_per_key=5)
    await WebSocketManager.unregister(state)
    assert WebSocketManager.count_for_key(3) == 0


@pytest.mark.asyncio
async def test_unregister_cancels_watchdog_task() -> None:
    ws = MagicMock()
    state = await WebSocketManager.register(ws, api_key_id=4, max_per_key=5)

    async def _sleep_forever() -> None:
        await asyncio.sleep(10)

    state.watchdog_task = asyncio.create_task(_sleep_forever())
    await WebSocketManager.unregister(state)
    # Give the cancel a moment to propagate.
    await asyncio.sleep(0)
    assert state.watchdog_task.cancelled() or state.watchdog_task.done()


@pytest.mark.asyncio
async def test_unregister_is_idempotent() -> None:
    """Calling unregister twice must not raise."""
    ws = MagicMock()
    state = await WebSocketManager.register(ws, api_key_id=5, max_per_key=5)
    await WebSocketManager.unregister(state)
    await WebSocketManager.unregister(state)
    assert WebSocketManager.count_for_key(5) == 0


@pytest.mark.asyncio
async def test_reset_for_test_clears_all_state() -> None:
    ws = MagicMock()
    await WebSocketManager.register(ws, api_key_id=100, max_per_key=5)
    await WebSocketManager.register(ws, api_key_id=200, max_per_key=5)
    await WebSocketManager.reset_for_test()
    assert WebSocketManager.count_for_key(100) == 0
    assert WebSocketManager.count_for_key(200) == 0
