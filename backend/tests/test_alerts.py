"""Tests for the alerts query endpoint (GET /api/v1/alerts)."""

from fastapi.testclient import TestClient


def _failed_login(user_id: str, second: int) -> dict:
    return {
        "user_id": user_id,
        "ip": "10.0.0.5",
        "timestamp": f"2026-07-31T12:00:{second:02d}Z",
        "event_type": "LOGIN_FAILURE",
        "status": "bad_password",
    }


def _burst_five_failures(client: TestClient, user_id: str) -> None:
    """POST 5 rapid failures for ``user_id`` — enough to cross the MEDIUM
    brute-force threshold and land exactly one alert in the DB."""
    for i in range(5):
        resp = client.post("/api/v1/log", json=_failed_login(user_id, i * 2))
        assert resp.status_code == 201


def test_empty_db_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts")

    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_by_user_id(client: TestClient) -> None:
    _burst_five_failures(client, "alice")
    _burst_five_failures(client, "bob")

    alice_alerts = client.get("/api/v1/alerts", params={"user_id": "alice"}).json()
    assert len(alice_alerts) == 1
    assert alice_alerts[0]["user_id"] == "alice"

    all_alerts = client.get("/api/v1/alerts").json()
    assert len(all_alerts) == 2


def test_filter_by_severity(client: TestClient) -> None:
    # A five-failure burst produces a MEDIUM brute-force alert.
    _burst_five_failures(client, "alice")

    medium = client.get("/api/v1/alerts", params={"severity": "MEDIUM"}).json()
    assert len(medium) == 1

    critical = client.get("/api/v1/alerts", params={"severity": "CRITICAL"}).json()
    assert critical == []
