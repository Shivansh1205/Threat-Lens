"""Tests that ingestion stores detection results without automatic LLM analysis."""

from fastapi.testclient import TestClient


def _five_failures_payload(i: int) -> dict:
    return {
        "user_id": "alice",
        "ip": "10.0.0.5",
        "timestamp": f"2026-07-31T12:00:{i * 2:02d}Z",
        "event_type": "LOGIN_FAILURE",
        "status": "bad_password",
    }


def test_ingestion_stores_alert_without_automatic_analysis(client: TestClient) -> None:
    for i in range(5):
        response = client.post("/api/v1/log", json=_five_failures_payload(i))
        assert response.status_code == 201

    assert len(response.json()["alert_ids"]) == 1
    alert = client.get("/api/v1/alerts", params={"limit": 1}).json()[0]
    assert alert["alert_type"] == "brute_force"
    assert alert["score"] > 0
    assert alert["explanation"] is None
    assert alert["mitigation_steps"] is None
