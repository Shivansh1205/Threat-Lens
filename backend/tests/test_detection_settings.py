from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.detection.settings import (
    get_detection_thresholds,
    load_persisted_thresholds,
    restore_environment_thresholds,
)
from app.main import app as fastapi_app
from app.models.detection_settings import DetectionSettingsRecord
from app.security import require_admin_key


def _login_failure(index: int) -> dict:
    return {
        "user_id": "threshold-user",
        "ip": "192.0.2.10",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "LOGIN_FAILURE",
        "status": "failed",
        "external_event_id": f"threshold-{index}",
    }


def test_get_returns_original_environment_defaults(client: TestClient) -> None:
    response = client.get("/api/v1/admin/detection-settings")
    assert response.status_code == 200
    body = response.json()
    assert body["is_overridden"] is False
    assert body["values"] == body["defaults"]
    assert body["values"]["brute_force"] == {
        "window_seconds": 60,
        "medium_threshold": 5,
        "high_threshold": 10,
        "critical_threshold": 20,
    }


def test_detection_settings_requires_admin_key(client: TestClient) -> None:
    fastapi_app.dependency_overrides.pop(require_admin_key, None)
    try:
        assert client.get("/api/v1/admin/detection-settings").status_code == 401
        assert client.get(
            "/api/v1/admin/detection-settings",
            headers={"X-ThreatLens-Admin-Key": "incorrect"},
        ).status_code == 401
        assert client.get(
            "/api/v1/admin/detection-settings",
            headers={"X-ThreatLens-Admin-Key": get_settings().ADMIN_API_KEY},
        ).status_code == 200
    finally:
        fastapi_app.dependency_overrides[require_admin_key] = lambda: None


def test_update_persists_applies_and_clears_active_windows(
    client: TestClient, db_session: Session
) -> None:
    for index in range(4):
        assert client.post("/api/v1/log", json=_login_failure(index)).json()["alert_ids"] == []

    payload = client.get("/api/v1/admin/detection-settings").json()["values"]
    payload["brute_force"].update(
        {"medium_threshold": 2, "high_threshold": 3, "critical_threshold": 4}
    )
    response = client.put("/api/v1/admin/detection-settings", json=payload)

    assert response.status_code == 200
    assert response.json()["is_overridden"] is True
    assert get_detection_thresholds().brute_force.medium_threshold == 2
    record = db_session.get(DetectionSettingsRecord, 1)
    assert record is not None
    assert record.values["brute_force"]["medium_threshold"] == 2

    # The four pre-update failures were cleared with the registry. The first
    # post-update failure is quiet; the second crosses the new limit.
    assert client.post("/api/v1/log", json=_login_failure(10)).json()["alert_ids"] == []
    assert len(client.post("/api/v1/log", json=_login_failure(11)).json()["alert_ids"]) == 1


def test_invalid_order_is_rejected_without_changing_active_values(client: TestClient) -> None:
    payload = client.get("/api/v1/admin/detection-settings").json()["values"]
    payload["path_probe"]["high_threshold"] = payload["path_probe"]["critical_threshold"]

    response = client.put("/api/v1/admin/detection-settings", json=payload)

    assert response.status_code == 422
    assert get_detection_thresholds().path_probe.high_threshold == 8


def test_reset_deletes_override_and_restores_defaults(
    client: TestClient, db_session: Session
) -> None:
    payload = client.get("/api/v1/admin/detection-settings").json()["values"]
    payload["unusual_ip"]["bootstrap_count"] = 8
    assert client.put("/api/v1/admin/detection-settings", json=payload).status_code == 200

    response = client.delete("/api/v1/admin/detection-settings")

    assert response.status_code == 200
    assert response.json()["is_overridden"] is False
    assert response.json()["values"] == response.json()["defaults"]
    assert db_session.get(DetectionSettingsRecord, 1) is None


def test_persisted_values_reload_into_runtime(client: TestClient, db_session: Session) -> None:
    payload = client.get("/api/v1/admin/detection-settings").json()["values"]
    payload["request_flood"].update({"high_threshold": 4, "critical_threshold": 6})
    client.put("/api/v1/admin/detection-settings", json=payload)
    restore_environment_thresholds()

    values, record = load_persisted_thresholds(db_session)

    assert record is not None
    assert values.request_flood.high_threshold == 4
    assert get_detection_thresholds().request_flood.critical_threshold == 6
