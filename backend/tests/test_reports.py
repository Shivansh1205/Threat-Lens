from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.user import User
from app.schemas.common import Severity


def _seed_alert(
    db: Session,
    *,
    alert_type: str,
    severity: Severity,
    created_at: datetime,
    message: str = "Detected threat",
    resolved: bool = False,
) -> None:
    if db.query(User).filter(User.user_id == "analyst-target").one_or_none() is None:
        db.add(User(user_id="analyst-target"))
        db.flush()
    db.add(
        Alert(
            user_id="analyst-target",
            alert_type=alert_type,
            severity=severity,
            score=80,
            raw_severity=severity,
            raw_score=75,
            message=message,
            evidence={"ip": "127.0.0.1"},
            resolved=resolved,
            created_at=created_at,
        )
    )
    db.commit()


def test_threat_metrics_groups_types_and_zero_fills(
    client: TestClient, db_session: Session
) -> None:
    start = datetime(2026, 8, 10, tzinfo=timezone.utc)
    _seed_alert(
        db_session,
        alert_type="brute_force",
        severity=Severity.HIGH,
        created_at=start + timedelta(minutes=5),
    )
    _seed_alert(
        db_session,
        alert_type="path_probe",
        severity=Severity.CRITICAL,
        created_at=start + timedelta(minutes=65),
        resolved=True,
    )

    response = client.get(
        "/api/v1/metrics/threats",
        params={
            "start": start.isoformat(),
            "end": (start + timedelta(hours=3)).isoformat(),
            "bucket_minutes": 60,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total": 2,
        "unresolved": 1,
        "high_critical": 2,
        "average_score": 80.0,
    }
    assert len(body["timeline"]) == 3
    assert body["timeline"][0]["by_type"] == {"brute_force": 1, "path_probe": 0}
    assert body["timeline"][2]["total"] == 0


def test_threat_metrics_filters_and_rejects_reversed_range(
    client: TestClient, db_session: Session
) -> None:
    start = datetime(2026, 8, 10, tzinfo=timezone.utc)
    _seed_alert(
        db_session,
        alert_type="request_flood",
        severity=Severity.CRITICAL,
        created_at=start + timedelta(hours=1),
    )
    _seed_alert(
        db_session,
        alert_type="unusual_ip",
        severity=Severity.MEDIUM,
        created_at=start + timedelta(hours=2),
    )
    params = {
        "start": start.isoformat(),
        "end": (start + timedelta(days=1)).isoformat(),
        "severity": "CRITICAL",
    }
    assert client.get("/api/v1/metrics/threats", params=params).json()["summary"]["total"] == 1
    reversed_response = client.get(
        "/api/v1/metrics/threats",
        params={"start": params["end"], "end": params["start"]},
    )
    assert reversed_response.status_code == 422


def test_csv_export_filters_and_escapes_formula_cells(
    client: TestClient, db_session: Session
) -> None:
    start = datetime(2026, 8, 10, tzinfo=timezone.utc)
    _seed_alert(
        db_session,
        alert_type="path_probe",
        severity=Severity.HIGH,
        created_at=start + timedelta(hours=1),
        message="=DANGEROUS()",
    )
    _seed_alert(
        db_session,
        alert_type="brute_force",
        severity=Severity.CRITICAL,
        created_at=start + timedelta(hours=2),
    )

    response = client.get(
        "/api/v1/reports/alerts.csv",
        params={
            "start": start.isoformat(),
            "end": (start + timedelta(days=1)).isoformat(),
            "alert_type": "path_probe",
        },
    )

    assert response.status_code == 200
    assert "attachment;" in response.headers["content-disposition"]
    assert "path_probe" in response.text
    assert "brute_force" not in response.text
    assert "'=DANGEROUS()" in response.text
