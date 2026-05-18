"""Unit tests for HeartbeatWatchdog (T10.3).

asyncio_mode = "auto" in pyproject.toml — @pytest.mark.asyncio decorators are
redundant but included for clarity, matching project convention.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.ws_quality.heartbeat import HeartbeatWatchdog
from app.services.ws_quality.manager import ConnectionState


def _make_state(last_ping: float) -> ConnectionState:
    ws = MagicMock()
    ws.close = AsyncMock()
    return ConnectionState(websocket=ws, api_key_id=42, last_ping_at=last_ping)


@pytest.mark.asyncio
async def test_touch_updates_last_ping_at() -> None:
    state = _make_state(last_ping=0.0)
    HeartbeatWatchdog.touch(state)
    assert state.last_ping_at > 0.0


@pytest.mark.asyncio
async def test_run_closes_socket_after_timeout() -> None:
    loop = asyncio.get_event_loop()
    # Set last_ping_at 10 seconds in the past so it is already stale.
    state = _make_state(last_ping=loop.time() - 10)
    task = asyncio.create_task(HeartbeatWatchdog.run(state, timeout_sec=1))
    await asyncio.wait_for(task, timeout=5)
    state.websocket.close.assert_awaited_once()
    args, kwargs = state.websocket.close.await_args
    assert kwargs.get("code", args[0] if args else None) == 1001


@pytest.mark.asyncio
async def test_run_does_not_close_when_fresh_ping() -> None:
    loop = asyncio.get_event_loop()
    state = _make_state(last_ping=loop.time())
    task = asyncio.create_task(HeartbeatWatchdog.run(state, timeout_sec=2))
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    state.websocket.close.assert_not_called()


@pytest.mark.asyncio
async def test_run_cancellation_does_not_close_socket() -> None:
    """Cancelling the watchdog task must not trigger ws.close."""
    loop = asyncio.get_event_loop()
    # Use a fresh ping so it won't naturally time out.
    state = _make_state(last_ping=loop.time())
    task = asyncio.create_task(HeartbeatWatchdog.run(state, timeout_sec=60))
    await asyncio.sleep(0)  # Let the task start.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    state.websocket.close.assert_not_called()


@pytest.mark.asyncio
async def test_touch_then_run_resets_timer() -> None:
    """If we touch() after a stale start, the run loop should not close early."""
    loop = asyncio.get_event_loop()
    # Start stale, then immediately touch to reset.
    state = _make_state(last_ping=loop.time() - 5)
    HeartbeatWatchdog.touch(state)  # Refreshes last_ping_at to now.
    task = asyncio.create_task(HeartbeatWatchdog.run(state, timeout_sec=2))
    await asyncio.sleep(0.5)  # Wait less than timeout.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    state.websocket.close.assert_not_called()
