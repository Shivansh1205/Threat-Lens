from datetime import datetime, timezone

from fastapi.testclient import TestClient


def event(index: int, *, path: str = "/api/data", status: int = 200) -> dict:
    return {
        "external_event_id": f"request-{index}",
        "user_id": "visitor_test",
        "ip": "127.0.0.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "API_CALL",
        "status": str(status),
        "endpoint": path,
        "http_method": "GET",
        "http_status": status,
    }


def test_batch_is_idempotent_and_updates_source(client: TestClient) -> None:
    payload = {
        "source_id": "portal",
        "source_name": "Demo portal",
        "events": [event(1)],
    }
    first = client.post("/api/v1/events/batch", json=payload)
    second = client.post("/api/v1/events/batch", json=payload)

    assert first.status_code == 200
    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1

    sources = client.get("/api/v1/sources").json()
    assert sources[0]["source_id"] == "portal"
    assert sources[0]["events_received"] == 1


def test_request_burst_creates_web_alert(client: TestClient) -> None:
    response = client.post(
        "/api/v1/events/batch",
        json={
            "source_id": "portal",
            "source_name": "Demo portal",
            "events": [event(index) for index in range(30)],
        },
    )
    assert response.status_code == 200
    assert response.json()["alert_ids"]
    alerts = client.get("/api/v1/alerts?alert_type=request_flood").json()
    assert len(alerts) == 1
    assert alerts[0]["evidence"]["count"] == 30


def test_metrics_are_authoritative(client: TestClient) -> None:
    client.post(
        "/api/v1/events/batch",
        json={
            "source_id": "portal",
            "source_name": "Demo portal",
            "events": [event(2)],
        },
    )
    response = client.get("/api/v1/metrics/summary")
    assert response.status_code == 200
    assert response.json()["events_24h"] == 1
