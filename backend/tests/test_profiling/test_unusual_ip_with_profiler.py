"""UnusualIpDetector tests against the persistent, profiler-backed profile.

These exercise the detector the way it's actually invoked in production: given
a BehaviorProfile row (built up by prior events), does `check()` correctly
read known_ips / bootstrap status straight from the DB — with no in-memory
state of its own?
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.detection.rules.unusual_ip import UnusualIpDetector
from app.models.behavior_profile import BehaviorProfile
from app.models.user import User
from app.profiling.profiler import BehaviorProfiler
from app.schemas.common import EventType

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


def _ensure_user(db: Session, user_id: str) -> None:
    if db.query(User).filter(User.user_id == user_id).one_or_none() is None:
        db.add(User(user_id=user_id, first_seen_at=BASE, last_seen_at=BASE))
        db.commit()


def _login(user_id: str, ts: datetime, ip: str = "10.0.0.1"):
    return make_event(user_id, EventType.LOGIN_SUCCESS, ts, ip=ip)


# ------------------------------------------------------------------- l


def test_unusual_ip_reads_from_profile(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    db_session.add(
        BehaviorProfile(
            user_id="carol",
            known_ips=["10.0.0.1"],
            login_count=4,  # past the default bootstrap count (3)
        )
    )
    db_session.commit()

    detector = UnusualIpDetector()
    event = _login("carol", BASE, ip="10.0.0.99")

    candidates = detector.check(event, db_session)

    assert len(candidates) == 1
    assert candidates[0].alert_type == "unusual_ip"
    assert "10.0.0.99" in candidates[0].message


# ------------------------------------------------------------------- m


def test_unusual_ip_bootstrap_from_profile(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    db_session.add(
        BehaviorProfile(
            user_id="carol",
            known_ips=["10.0.0.1"],
            login_count=2,  # below the default bootstrap count (3)
        )
    )
    db_session.commit()

    detector = UnusualIpDetector()
    event = _login("carol", BASE, ip="10.0.0.99")

    candidates = detector.check(event, db_session)

    assert candidates == []


# ------------------------------------------------------------------- n


def test_unusual_ip_persists_across_restart(db_session: Session) -> None:
    """The key test: known IPs survive a simulated process restart because
    they live in the DB, not in the detector's memory.
    """
    _ensure_user(db_session, "carol")

    # Build up state the normal way: 4 logins from IP A, via the profiler,
    # past the bootstrap count.
    setup_profiler = BehaviorProfiler(db_session, alpha=0.05)
    for i in range(4):
        setup_profiler.update(
            _login("carol", BASE + timedelta(days=i), ip="10.0.0.1")
        )

    # "Restart": fresh profiler, fresh detector — no shared Python objects,
    # no shared in-memory dicts. Only the DB row connects them.
    fresh_detector = UnusualIpDetector()
    event = _login("carol", BASE + timedelta(days=4), ip="10.0.0.55")

    candidates = fresh_detector.check(event, db_session)

    assert len(candidates) == 1
    assert candidates[0].alert_type == "unusual_ip"
    assert "10.0.0.55" in candidates[0].message
