"""Tests for `/ws/alerts` via FastAPI's TestClient WebSocket support.

INVESTIGATED, not assumed: ``TestClient.websocket_connect(...)`` requires
the TestClient to be entered as a context manager (``with TestClient(app) as
c:``), because that's what starts the app's ``lifespan`` — without it,
Starlette's WebSocket test session has no running app/event loop to connect
to. The shared ``client`` fixture (conftest.py) was updated in this phase to
enter ``TestClient`` as a context manager for exactly this reason (and
because Phase 7a's lifespan handler is also what captures the event loop for
``WebSocketManager.schedule_broadcast``).

The full round-trip test below (``test_alert_broadcast_reaches_connected_client``)
confirms empirically that broadcasting works end-to-end even though the
broadcast is dispatched from a *sync* endpoint on the threadpool via
``asyncio.run_coroutine_threadsafe`` (fire-and-forget) while the WebSocket
connection itself is being driven on the main/portal loop that TestClient
sets up — i.e. the cross-thread bridge in WebSocketManager actually works
under TestClient's execution model, not just in theory.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_can_connect_to_ws_alerts(client: TestClient) -> None:
    with client.websocket_connect("/ws/alerts") as ws:
        pass  # connecting and cleanly exiting without error is the assertion


def _five_failures_payload(i: int) -> dict:
    return {
        "user_id": "alice",
        "ip": "10.0.0.5",
        "timestamp": f"2026-07-31T12:00:{i * 2:02d}Z",
        "event_type": "LOGIN_FAILURE",
        "status": "bad_password",
    }


def test_alert_broadcast_reaches_connected_client(client: TestClient) -> None:
    """End-to-end proof: POST /api/v1/log triggering an alert results in a
    message being pushed to an already-connected /ws/alerts client.
    """
    with client.websocket_connect("/ws/alerts") as ws:
        last_resp = None
        for i in range(5):
            last_resp = client.post("/api/v1/log", json=_five_failures_payload(i))
            assert last_resp.status_code == 201

        alert_ids = last_resp.json()["alert_ids"]
        assert len(alert_ids) == 1  # the 5th failure crosses the MEDIUM threshold

        message = ws.receive_json()

    assert message["id"] == alert_ids[0]
    assert message["user_id"] == "alice"
    assert message["alert_type"] == "brute_force"
    assert message["severity"] == "MEDIUM"
    assert message["score"] == 45
    assert "message" in message
    assert "created_at" in message
    # Explanation/mitigation fields are deliberately not part of the push
    # payload (see api/logs.py's design note) — confirm they're absent.
    assert "explanation" not in message
    assert "mitigation_steps" not in message


def test_broadcast_not_received_by_disconnected_client(client: TestClient) -> None:
    """A client that has already disconnected must not cause any error for
    the alert-triggering request, and obviously receives nothing.
    """
    with client.websocket_connect("/ws/alerts"):
        pass  # connect then immediately let the `with` block close it

    for i in range(5):
        resp = client.post("/api/v1/log", json=_five_failures_payload(i))
        assert resp.status_code == 201  # must succeed even with zero live clients
