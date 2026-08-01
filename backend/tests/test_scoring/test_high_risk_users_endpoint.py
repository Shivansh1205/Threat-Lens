"""Tests for GET /api/v1/users/high-risk."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.behavior_profile import BehaviorProfile
from app.models.user import User

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed_user_and_profile(
    db_session: Session,
    user_id: str,
    user_risk_score: float,
    login_count: int = 1,
    known_ips: list[str] | None = None,
) -> None:
    db_session.add(User(user_id=user_id, first_seen_at=NOW, last_seen_at=NOW))
    db_session.add(
        BehaviorProfile(
            user_id=user_id,
            known_ips=known_ips or [],
            login_count=login_count,
            deviation_score=0.0,
            user_risk_score=user_risk_score,
            last_event_at=NOW,
        )
    )
    db_session.commit()


def test_empty_db_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/v1/users/high-risk")

    assert resp.status_code == 200
    assert resp.json() == []


def test_users_with_zero_risk_excluded(client: TestClient, db_session: Session) -> None:
    _seed_user_and_profile(db_session, "quiet_user", user_risk_score=0.0)

    resp = client.get("/api/v1/users/high-risk")

    assert resp.status_code == 200
    assert resp.json() == []


def test_multiple_users_ordered_descending(client: TestClient, db_session: Session) -> None:
    _seed_user_and_profile(db_session, "low_risk", user_risk_score=10.0)
    _seed_user_and_profile(db_session, "high_risk", user_risk_score=80.0)
    _seed_user_and_profile(db_session, "mid_risk", user_risk_score=45.0)
    _seed_user_and_profile(db_session, "zero_risk", user_risk_score=0.0)

    resp = client.get("/api/v1/users/high-risk")

    assert resp.status_code == 200
    body = resp.json()
    assert [row["user_id"] for row in body] == ["high_risk", "mid_risk", "low_risk"]
    assert body[0]["user_risk_score"] == 80.0
    # Response shape sanity.
    assert set(body[0].keys()) == {
        "user_id",
        "user_risk_score",
        "login_count",
        "known_ip_count",
        "last_event_at",
    }


def test_limit_parameter_respected(client: TestClient, db_session: Session) -> None:
    for i in range(5):
        _seed_user_and_profile(db_session, f"user_{i}", user_risk_score=float(10 + i))

    resp = client.get("/api/v1/users/high-risk", params={"limit": 2})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # Highest two: user_4 (14.0), user_3 (13.0).
    assert [row["user_id"] for row in body] == ["user_4", "user_3"]


def test_known_ip_count_reflects_known_ips(client: TestClient, db_session: Session) -> None:
    _seed_user_and_profile(
        db_session, "scanner", user_risk_score=50.0, known_ips=["10.0.0.1", "10.0.0.2"]
    )

    resp = client.get("/api/v1/users/high-risk")

    assert resp.status_code == 200
    assert resp.json()[0]["known_ip_count"] == 2
