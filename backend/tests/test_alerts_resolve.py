"""Tests for PATCH /api/v1/alerts/{id}/resolve and /unresolve."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def _failed_login(user_id: str, second: int) -> dict:
    return {
        "user_id": user_id,
        "ip": "10.0.0.5",
        "timestamp": f"2026-07-31T12:00:{second:02d}Z",
        "event_type": "LOGIN_FAILURE",
        "status": "bad_password",
    }


def _create_one_alert(client: TestClient, user_id: str = "alice") -> str:
    """POST 5 rapid failures — crosses the MEDIUM brute-force threshold,
    producing exactly one alert. Returns its id."""
    for i in range(5):
        resp = client.post("/api/v1/log", json=_failed_login(user_id, i * 2))
        assert resp.status_code == 201
    alert_ids = resp.json()["alert_ids"]
    assert len(alert_ids) == 1
    return alert_ids[0]


def test_resolve_existing_alert(client: TestClient) -> None:
    alert_id = _create_one_alert(client)

    resp = client.patch(f"/api/v1/alerts/{alert_id}/resolve")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == alert_id
    assert body["resolved"] is True
    assert body["resolved_at"] is not None


def test_resolve_already_resolved_alert_is_idempotent(client: TestClient) -> None:
    alert_id = _create_one_alert(client)

    first = client.patch(f"/api/v1/alerts/{alert_id}/resolve")
    assert first.status_code == 200
    first_resolved_at = first.json()["resolved_at"]

    # A real (if tiny) delay so a bug that DID reset resolved_at would be
    # detectable via a changed timestamp, not masked by same-millisecond luck.
    time.sleep(0.05)

    second = client.patch(f"/api/v1/alerts/{alert_id}/resolve")
    assert second.status_code == 200
    assert second.json()["resolved"] is True
    assert second.json()["resolved_at"] == first_resolved_at


def test_resolve_nonexistent_alert_returns_404(client: TestClient) -> None:
    resp = client.patch("/api/v1/alerts/00000000-0000-0000-0000-000000000000/resolve")
    assert resp.status_code == 404


def test_unresolve_clears_resolved_and_resolved_at(client: TestClient) -> None:
    alert_id = _create_one_alert(client)
    client.patch(f"/api/v1/alerts/{alert_id}/resolve")

    resp = client.patch(f"/api/v1/alerts/{alert_id}/unresolve")

    assert resp.status_code == 200
    body = resp.json()
    assert body["resolved"] is False
    assert body["resolved_at"] is None


def test_unresolve_already_unresolved_alert_is_idempotent(client: TestClient) -> None:
    alert_id = _create_one_alert(client)

    resp = client.patch(f"/api/v1/alerts/{alert_id}/unresolve")

    assert resp.status_code == 200
    assert resp.json()["resolved"] is False
    assert resp.json()["resolved_at"] is None


def test_unresolve_nonexistent_alert_returns_404(client: TestClient) -> None:
    resp = client.patch("/api/v1/alerts/00000000-0000-0000-0000-000000000000/unresolve")
    assert resp.status_code == 404
