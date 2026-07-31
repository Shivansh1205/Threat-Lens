"""Tests for the log ingestion endpoint (POST /api/v1/log)."""

from fastapi.testclient import TestClient

from app.models.user import User


def _event(**overrides) -> dict:
    base = {
        "user_id": "alice",
        "ip": "10.0.0.5",
        "timestamp": "2026-07-31T12:00:00Z",
        "event_type": "LOGIN_SUCCESS",
        "status": "ok",
    }
    base.update(overrides)
    return base


def test_login_success_creates_user_no_alert(client: TestClient, db_session) -> None:
    resp = client.post("/api/v1/log", json=_event())

    assert resp.status_code == 201
    body = resp.json()
    assert body["alert_ids"] == []
    assert body["event_id"]

    # User row was created.
    user = db_session.query(User).filter(User.user_id == "alice").one_or_none()
    assert user is not None


def test_single_failure_no_alert(client: TestClient) -> None:
    """One LOGIN_FAILURE is below every threshold — nothing should fire."""
    resp = client.post(
        "/api/v1/log",
        json=_event(event_type="LOGIN_FAILURE", status="bad_password"),
    )

    assert resp.status_code == 201
    assert resp.json()["alert_ids"] == []
    assert client.get("/api/v1/alerts").json() == []


def test_five_rapid_failures_emit_medium_alert(client: TestClient) -> None:
    """Crossing the MEDIUM brute-force threshold produces exactly one alert."""
    for i in range(5):
        # Distinct timestamps within the 60s window.
        payload = _event(
            event_type="LOGIN_FAILURE",
            status="bad_password",
            timestamp=f"2026-07-31T12:00:{i * 2:02d}Z",
        )
        resp = client.post("/api/v1/log", json=payload)
        assert resp.status_code == 201

    alerts = client.get("/api/v1/alerts").json()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["alert_type"] == "brute_force"
    assert alert["severity"] == "MEDIUM"
    assert alert["score"] == 45


def test_missing_required_field_returns_422(client: TestClient) -> None:
    payload = _event()
    del payload["user_id"]

    resp = client.post("/api/v1/log", json=payload)

    assert resp.status_code == 422


def test_unknown_field_returns_422(client: TestClient) -> None:
    resp = client.post("/api/v1/log", json=_event(surprise="unexpected"))

    assert resp.status_code == 422
