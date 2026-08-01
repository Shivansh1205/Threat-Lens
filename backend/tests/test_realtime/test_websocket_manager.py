"""Tests for WebSocketManager — mock WebSocket objects, no real sockets
except where noted in test_websocket_endpoint.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.realtime.websocket_manager import WebSocketManager

# --------------------------------------------------------------------- connect


@pytest.mark.anyio
async def test_connect_returns_unique_client_id_and_stores_connection() -> None:
    manager = WebSocketManager()
    ws1, ws2 = AsyncMock(), AsyncMock()

    id1 = await manager.connect(ws1)
    id2 = await manager.connect(ws2)

    assert id1 != id2
    assert isinstance(id1, str) and isinstance(id2, str)
    ws1.accept.assert_awaited_once()
    ws2.accept.assert_awaited_once()
    assert manager.connection_count == 2


# ------------------------------------------------------------------ disconnect


@pytest.mark.anyio
async def test_disconnect_removes_client() -> None:
    manager = WebSocketManager()
    client_id = await manager.connect(AsyncMock())
    assert manager.connection_count == 1

    manager.disconnect(client_id)

    assert manager.connection_count == 0


def test_disconnect_unknown_client_id_is_safe() -> None:
    manager = WebSocketManager()
    manager.disconnect("does-not-exist")  # must not raise


# -------------------------------------------------------------------- broadcast


@pytest.mark.anyio
async def test_broadcast_sends_to_all_connected_clients() -> None:
    manager = WebSocketManager()
    ws1, ws2, ws3 = AsyncMock(), AsyncMock(), AsyncMock()
    await manager.connect(ws1)
    await manager.connect(ws2)
    await manager.connect(ws3)

    message = {"alert_type": "brute_force", "severity": "HIGH"}
    await manager.broadcast(message)

    ws1.send_json.assert_awaited_once_with(message)
    ws2.send_json.assert_awaited_once_with(message)
    ws3.send_json.assert_awaited_once_with(message)


@pytest.mark.anyio
async def test_broadcast_one_failing_client_does_not_block_others_and_is_removed() -> None:
    manager = WebSocketManager()
    good1, bad, good2 = AsyncMock(), AsyncMock(), AsyncMock()
    bad.send_json.side_effect = RuntimeError("connection reset by peer")

    id_good1 = await manager.connect(good1)
    id_bad = await manager.connect(bad)
    id_good2 = await manager.connect(good2)

    await manager.broadcast({"x": 1})  # must not raise despite bad's failure

    good1.send_json.assert_awaited_once()
    good2.send_json.assert_awaited_once()
    bad.send_json.assert_awaited_once()  # it was attempted
    assert manager.connection_count == 2
    assert manager._connections.get(id_bad) is None
    assert id_good1 in manager._connections
    assert id_good2 in manager._connections


@pytest.mark.anyio
async def test_broadcast_with_no_clients_does_nothing() -> None:
    manager = WebSocketManager()
    await manager.broadcast({"x": 1})  # must not raise on an empty manager


# ---------------------------------------------------------------- send_personal


@pytest.mark.anyio
async def test_send_personal_sends_only_to_specified_client() -> None:
    manager = WebSocketManager()
    ws1, ws2 = AsyncMock(), AsyncMock()
    id1 = await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.send_personal(id1, {"hello": "there"})

    ws1.send_json.assert_awaited_once_with({"hello": "there"})
    ws2.send_json.assert_not_awaited()


@pytest.mark.anyio
async def test_send_personal_unknown_client_id_is_safe() -> None:
    manager = WebSocketManager()
    await manager.send_personal("no-such-client", {"x": 1})  # must not raise


@pytest.mark.anyio
async def test_send_personal_failure_removes_client() -> None:
    manager = WebSocketManager()
    ws = AsyncMock()
    ws.send_json.side_effect = RuntimeError("gone")
    client_id = await manager.connect(ws)

    await manager.send_personal(client_id, {"x": 1})

    assert manager.connection_count == 0


# ------------------------------------------------------- cross-thread scheduling


def test_schedule_broadcast_without_loop_logs_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = WebSocketManager()
    with caplog.at_level("WARNING"):
        manager.schedule_broadcast({"x": 1})  # no loop captured yet

    assert any("no event loop captured" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_schedule_broadcast_delivers_via_the_captured_loop() -> None:
    """Exercises the actual asyncio.run_coroutine_threadsafe bridge (the
    same code path api/logs.py's sync endpoint uses), rather than calling
    broadcast() directly.
    """
    manager = WebSocketManager()
    manager.set_loop(asyncio.get_running_loop())
    ws = AsyncMock()
    await manager.connect(ws)

    manager.schedule_broadcast({"x": 1})

    # schedule_broadcast is fire-and-forget from the caller's perspective —
    # give the loop a tick to actually run the scheduled coroutine.
    for _ in range(20):
        if ws.send_json.await_count:
            break
        await asyncio.sleep(0.01)

    ws.send_json.assert_awaited_once_with({"x": 1})
