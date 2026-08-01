"""Tests for POST /api/v1/admin/decay-now."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.behavior_profile import BehaviorProfile
from app.models.user import User


def _seed_profile(db_session: Session, user_id: str, user_risk_score: float, updated_at) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(User(user_id=user_id, first_seen_at=now, last_seen_at=now))
    db_session.add(
        BehaviorProfile(
            user_id=user_id,
            known_ips=[],
            deviation_score=0.0,
            user_risk_score=user_risk_score,
            last_event_at=now,
            updated_at=updated_at,
        )
    )
    db_session.commit()


def test_decay_now_returns_expected_shape_on_empty_db(client: TestClient) -> None:
    resp = client.post("/api/v1/admin/decay-now")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"profiles_processed", "profiles_decayed", "total_score_removed"}
    assert body == {"profiles_processed": 0, "profiles_decayed": 0, "total_score_removed": 0.0}


def test_decay_now_actually_decays_a_backdated_profile(
    client: TestClient, db_session: Session
) -> None:
    backdated = datetime.now(timezone.utc) - timedelta(days=30)
    _seed_profile(db_session, "alice", user_risk_score=50.0, updated_at=backdated)

    resp = client.post("/api/v1/admin/decay-now")

    assert resp.status_code == 200
    body = resp.json()
    assert body["profiles_processed"] == 1
    assert body["profiles_decayed"] == 1
    assert body["total_score_removed"] > 0.0

    profile = (
        db_session.query(BehaviorProfile).filter(BehaviorProfile.user_id == "alice").one()
    )
    assert profile.user_risk_score < 50.0
    assert profile.user_risk_score == 50.0 - body["total_score_removed"]


def test_decay_now_is_idempotent_no_op_on_second_immediate_call(
    client: TestClient, db_session: Session
) -> None:
    """Calling it twice back-to-back: the second call should find the
    profile's updated_at freshly reset by the first call, so it decays
    negligibly (not a second full decay of the original amount)."""
    backdated = datetime.now(timezone.utc) - timedelta(days=30)
    _seed_profile(db_session, "bob", user_risk_score=50.0, updated_at=backdated)

    first = client.post("/api/v1/admin/decay-now").json()
    second = client.post("/api/v1/admin/decay-now").json()

    assert first["profiles_decayed"] == 1
    # Second call happens moments after the first, so days_elapsed is ~0 —
    # score is at or below the floor's worth of change, not another chunk.
    assert second["total_score_removed"] < first["total_score_removed"] * 0.01
