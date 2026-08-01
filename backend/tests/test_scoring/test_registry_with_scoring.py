"""Integration tests: DetectorRegistry + RiskScorer, through real persistence.

Complements test_detection/test_registry.py (which pins deviation_score at
0.0 throughout) by exercising the case that actually matters for Phase 5:
a user with behavioral context that changes the final persisted alert.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.detection.registry import DetectorRegistry
from app.detection.rules import BruteForceDetector, PortScanDetector, UnusualIpDetector
from app.models.alert import Alert
from app.models.behavior_profile import BehaviorProfile
from app.models.user import User
from app.schemas.common import EventType

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _fresh_registry() -> DetectorRegistry:
    return DetectorRegistry([BruteForceDetector(), PortScanDetector(), UnusualIpDetector()])


def _seed_user(db_session: Session, user_id: str) -> None:
    db_session.add(User(user_id=user_id, first_seen_at=BASE, last_seen_at=BASE))
    db_session.commit()


def _profile(db_session: Session, user_id: str, deviation_score: float) -> BehaviorProfile:
    profile = BehaviorProfile(
        user_id=user_id,
        known_ips=[],
        deviation_score=deviation_score,
        user_risk_score=0.0,
    )
    db_session.add(profile)
    db_session.flush()
    return profile


def _five_failures(db_session: Session, reg: DetectorRegistry, profile: BehaviorProfile) -> Alert:
    """Feed 5 rapid LOGIN_FAILUREs for profile.user_id — crosses the MEDIUM
    brute-force threshold (raw score 45). Returns the resulting Alert.
    """
    last_alerts: list[Alert] = []
    for i in range(5):
        ev = make_event(profile.user_id, EventType.LOGIN_FAILURE, BASE.replace(second=i * 2))
        db_session.add(ev)
        db_session.flush()
        last_alerts = reg.run_all(ev, db_session, profile)
        db_session.commit()

    assert len(last_alerts) == 1
    return last_alerts[0]


def test_high_deviation_user_gets_escalated_score(db_session: Session) -> None:
    """Same brute-force MEDIUM trigger, but for a user with deviation_score
    pinned at 1.0 (maximum novelty) — the persisted alert must show the
    risk-adjusted score/severity, different from Phase 3's raw expectation
    (score=45, severity=MEDIUM), while still preserving what the detector
    itself originally said.
    """
    _seed_user(db_session, "mallory")
    profile = _profile(db_session, "mallory", deviation_score=1.0)
    reg = _fresh_registry()

    alert = _five_failures(db_session, reg, profile)

    # Detector's original call, preserved verbatim.
    assert alert.raw_score == 45
    assert alert.raw_severity.name == "MEDIUM"

    # Risk-adjusted final values differ from the raw Phase 3 expectation:
    # 45 + 1.0 * 0.3 * (100 - 45) = 61.5 -> round -> 62 -> HIGH bucket.
    assert alert.score == 62
    assert alert.severity.name == "HIGH"
    assert alert.score != alert.raw_score
    assert alert.severity != alert.raw_severity

    # Persisted user_risk_score reflects this one alert's contribution.
    assert profile.user_risk_score > 0.0


def test_zero_deviation_user_scoring_is_a_no_op(db_session: Session) -> None:
    """Same sequence, deviation_score=0.0 — adjusted must equal raw exactly."""
    _seed_user(db_session, "cleanuser")
    profile = _profile(db_session, "cleanuser", deviation_score=0.0)
    reg = _fresh_registry()

    alert = _five_failures(db_session, reg, profile)

    assert alert.raw_score == 45
    assert alert.raw_severity.name == "MEDIUM"
    assert alert.score == alert.raw_score == 45
    assert alert.severity == alert.raw_severity
    assert alert.severity.name == "MEDIUM"
