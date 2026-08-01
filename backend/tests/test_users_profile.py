"""Tests for GET /api/v1/users/{user_id}/profile.

Task 2 decision (see this feature's report / CHANGELOG): a user's alert
history is already fully covered by the existing `GET /api/v1/alerts?
user_id=X` (with the sort_by/sort_order/resolved/alert_type params this
same round of work added — see test_alerts.py) — no parallel endpoint was
built here. Nothing to test for that decision beyond the existing
test_alerts.py coverage, which already exercises `user_id` filtering.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _login(user_id: str, second: int, ip: str = "10.0.0.5") -> dict:
    return {
        "user_id": user_id,
        "ip": ip,
        "timestamp": f"2026-07-31T12:00:{second:02d}Z",
        "event_type": "LOGIN_SUCCESS",
        "status": "ok",
    }


def test_get_profile_for_existing_user(client: TestClient) -> None:
    for i in range(3):
        resp = client.post("/api/v1/log", json=_login("alice", i * 2))
        assert resp.status_code == 201

    resp = client.get("/api/v1/users/alice/profile")

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "alice"
    assert body["login_count"] == 3
    assert body["known_ips"] == ["10.0.0.5"]
    assert body["total_sessions"] == 0
    assert body["deviation_score"] >= 0.0
    assert body["user_risk_score"] == 0.0  # no alerts triggered
    assert body["typical_login_hour"] is not None
    assert body["created_at"] is not None
    assert body["updated_at"] is not None
    assert body["last_event_at"] is not None


def test_get_profile_for_user_with_no_profile_returns_404(client: TestClient) -> None:
    resp = client.get("/api/v1/users/nobody/profile")
    assert resp.status_code == 404


def test_days_since_first_seen_is_non_negative_and_present(client: TestClient) -> None:
    resp = client.post("/api/v1/log", json=_login("alice", 0))
    assert resp.status_code == 201

    resp = client.get("/api/v1/users/alice/profile")

    assert resp.status_code == 200
    body = resp.json()
    assert "days_since_first_seen" in body
    # Created moments ago (real wall-clock, since created_at has no
    # server-controllable override) — must be a small non-negative float,
    # not minutes/hours/days off.
    assert 0.0 <= body["days_since_first_seen"] < 0.01


def test_known_ips_accumulate_across_multiple_logins_different_ips(client: TestClient) -> None:
    client.post("/api/v1/log", json=_login("alice", 0, ip="10.0.0.1"))
    client.post("/api/v1/log", json=_login("alice", 2, ip="10.0.0.2"))

    resp = client.get("/api/v1/users/alice/profile")

    assert resp.status_code == 200
    assert set(resp.json()["known_ips"]) == {"10.0.0.1", "10.0.0.2"}
