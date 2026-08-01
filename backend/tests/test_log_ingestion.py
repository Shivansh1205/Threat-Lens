"""Tests for the log ingestion endpoint (POST /api/v1/log)."""

from fastapi.testclient import TestClient

from app.models.behavior_profile import BehaviorProfile
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


def test_ingestion_builds_behavior_profile(client: TestClient, db_session) -> None:
    """POSTing events for a user should build up their persistent profile."""
    for i in range(5):
        payload = _event(
            user_id="dave",
            ip="10.0.2.1",
            timestamp=f"2026-07-31T09:00:{i * 2:02d}Z",
        )
        resp = client.post("/api/v1/log", json=payload)
        assert resp.status_code == 201

    profile = (
        db_session.query(BehaviorProfile).filter(BehaviorProfile.user_id == "dave").one()
    )
    assert profile.login_count == 5
    assert "10.0.2.1" in profile.known_ips


def test_unusual_ip_alert_fires_through_full_ingestion_endpoint(client: TestClient) -> None:
    """Regression guard for the profiler/detector pipeline-ordering fix.

    BehaviorProfiler.update() unconditionally folds the current event's IP into
    known_ips. If the ingestion endpoint called profiler.update() *before*
    running detection, UnusualIpDetector would always find its own event's IP
    already "known" and could never fire — silently neutering the detector in
    production even though isolated unit tests (which call detector.check()
    directly, without an update() for the same event) would still pass. This
    test exercises the real endpoint end-to-end to catch exactly that class of
    bug.
    """
    # 3 bootstrap logins from one IP (default UNUSUAL_IP_BOOTSTRAP_COUNT=3).
    for i in range(3):
        resp = client.post(
            "/api/v1/log",
            json=_event(
                user_id="erin",
                ip="10.0.3.1",
                timestamp=f"2026-07-31T09:{i:02d}:00Z",
            ),
        )
        assert resp.status_code == 201
        assert resp.json()["alert_ids"] == []

    # 4th login from a brand-new IP — must alert.
    resp = client.post(
        "/api/v1/log",
        json=_event(user_id="erin", ip="10.0.3.99", timestamp="2026-07-31T09:10:00Z"),
    )
    assert resp.status_code == 201
    assert len(resp.json()["alert_ids"]) == 1

    alerts = client.get("/api/v1/alerts", params={"user_id": "erin"}).json()
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "unusual_ip"
    assert "10.0.3.99" in alerts[0]["message"]


def test_missing_required_field_returns_422(client: TestClient) -> None:
    payload = _event()
    del payload["user_id"]

    resp = client.post("/api/v1/log", json=payload)

    assert resp.status_code == 422


def test_unknown_field_returns_422(client: TestClient) -> None:
    resp = client.post("/api/v1/log", json=_event(surprise="unexpected"))

    assert resp.status_code == 422
