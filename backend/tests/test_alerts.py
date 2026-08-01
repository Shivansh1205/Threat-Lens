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


def test_no_new_params_matches_pre_existing_behavior(client: TestClient) -> None:
    """Backward-compatibility guard: a caller that only ever passes `limit`
    (e.g. the dashboard's useAlertStream initial fetch) must see exactly the
    same most-recent-first ordering as before the resolved/alert_type/sort_*
    params existed — none of them default to filtering/reordering anything.
    """
    _burst_five_failures(client, "alice")
    _burst_five_failures(client, "bob")

    resp = client.get("/api/v1/alerts", params={"limit": 200})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # Most-recent-first (created_at desc) — bob's burst ran after alice's.
    assert body[0]["user_id"] == "bob"
    assert body[1]["user_id"] == "alice"


def test_filter_by_resolved_true_returns_only_resolved(client: TestClient) -> None:
    _burst_five_failures(client, "alice")
    alert_id = client.get("/api/v1/alerts", params={"user_id": "alice"}).json()[0]["id"]
    _burst_five_failures(client, "bob")

    client.patch(f"/api/v1/alerts/{alert_id}/resolve")

    resolved = client.get("/api/v1/alerts", params={"resolved": True}).json()
    assert len(resolved) == 1
    assert resolved[0]["id"] == alert_id
    assert resolved[0]["resolved"] is True

    unresolved = client.get("/api/v1/alerts", params={"resolved": False}).json()
    assert len(unresolved) == 1
    assert unresolved[0]["resolved"] is False

    both = client.get("/api/v1/alerts").json()
    assert len(both) == 2


def test_filter_by_alert_type(client: TestClient) -> None:
    _burst_five_failures(client, "alice")  # alert_type == "brute_force"

    brute_force = client.get("/api/v1/alerts", params={"alert_type": "brute_force"}).json()
    assert len(brute_force) == 1
    assert brute_force[0]["alert_type"] == "brute_force"

    port_scan = client.get("/api/v1/alerts", params={"alert_type": "port_scan"}).json()
    assert port_scan == []


def test_sort_by_score_ascending(client: TestClient) -> None:
    # alice: 5 failures -> one MEDIUM alert. bob: 10 failures -> MEDIUM + HIGH.
    _burst_five_failures(client, "alice")
    for i in range(10):
        resp = client.post(
            "/api/v1/log",
            json={
                "user_id": "bob", "ip": "10.0.0.5", "timestamp": f"2026-07-31T13:00:{i * 2:02d}Z",
                "event_type": "LOGIN_FAILURE", "status": "bad_password",
            },
        )
        assert resp.status_code == 201

    resp = client.get("/api/v1/alerts", params={"sort_by": "score", "sort_order": "asc"})

    assert resp.status_code == 200
    scores = [a["score"] for a in resp.json()]
    assert scores == sorted(scores)
    assert len(scores) == 3  # alice's MEDIUM, bob's MEDIUM, bob's HIGH


def test_sort_by_created_at_ascending(client: TestClient) -> None:
    _burst_five_failures(client, "alice")
    _burst_five_failures(client, "bob")

    resp = client.get("/api/v1/alerts", params={"sort_by": "created_at", "sort_order": "asc"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["user_id"] == "alice"  # created first
    assert body[1]["user_id"] == "bob"


def test_sort_by_invalid_value_returns_422(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts", params={"sort_by": "explanation"})
    assert resp.status_code == 422
