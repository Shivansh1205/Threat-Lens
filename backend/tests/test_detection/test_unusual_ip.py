"""UnusualIpDetector unit tests.

Phase 4: the detector is now stateless — known IPs and login counts live in
the persistent BehaviorProfile. These tests set up that state through
BehaviorProfiler (the same way the real ingestion pipeline does: detect, then
update) rather than poking at detector-internal dicts, since those no longer
exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.detection.base import AlertCandidate
from app.detection.rules.unusual_ip import UnusualIpDetector
from app.models.user import User
from app.profiling.profiler import BehaviorProfiler
from app.schemas.common import EventType, Severity

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def _ensure_user(db: Session, user_id: str) -> None:
    if db.query(User).filter(User.user_id == user_id).one_or_none() is None:
        db.add(User(user_id=user_id, first_seen_at=BASE, last_seen_at=BASE))
        db.commit()


def _login(user_id: str, ip: str, t: float, event_type: EventType = EventType.LOGIN_SUCCESS):
    return make_event(user_id, event_type, BASE + timedelta(seconds=t), ip=ip)


def _ingest(
    detector: UnusualIpDetector, profiler: BehaviorProfiler, event, db: Session
) -> list[AlertCandidate]:
    """Mirror the real pipeline order for one event: detect, then update the
    profile. Use this for "setup" events whose side effects the next event in
    the test depends on (e.g. a new IP must get folded into known_ips before
    the following event checks membership again)."""
    candidates = detector.check(event, db)
    profiler.update(event)
    return candidates


def test_bootstrap_first_three_logins_no_candidates(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    detector = UnusualIpDetector()
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    outs = [
        _ingest(detector, profiler, _login("carol", "10.0.0.1", i * 60), db_session)
        for i in range(3)
    ]
    assert all(x == [] for x in outs)


def test_fourth_login_from_known_ip_no_candidate(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    detector = UnusualIpDetector()
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    for i in range(3):
        _ingest(detector, profiler, _login("carol", "10.0.0.1", i * 60), db_session)

    out = detector.check(_login("carol", "10.0.0.1", 240), db_session)
    assert out == []


def test_fourth_login_from_new_ip_emits_low(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    detector = UnusualIpDetector()
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    for i in range(3):
        _ingest(detector, profiler, _login("carol", "10.0.0.1", i * 60), db_session)

    out = detector.check(_login("carol", "10.0.0.99", 240), db_session)
    assert len(out) == 1
    assert out[0].alert_type == "unusual_ip"
    assert out[0].severity == Severity.LOW
    assert out[0].score == 30
    assert "10.0.0.99" in out[0].message


def test_second_login_from_new_ip_not_reflagged(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    detector = UnusualIpDetector()
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    for i in range(3):
        _ingest(detector, profiler, _login("carol", "10.0.0.1", i * 60), db_session)

    # First sighting of the new IP: alert, and (via _ingest) the profile now
    # remembers it.
    first = _ingest(detector, profiler, _login("carol", "10.0.0.99", 240), db_session)
    second = detector.check(_login("carol", "10.0.0.99", 300), db_session)

    assert len(first) == 1
    assert second == []


def test_users_tracked_independently(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    _ensure_user(db_session, "bob")
    detector = UnusualIpDetector()
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    # Alice bootstraps on IP A, Bob bootstraps on IP B. Their known-sets don't leak.
    for i in range(3):
        _ingest(detector, profiler, _login("alice", "10.0.0.1", i * 60), db_session)
        _ingest(detector, profiler, _login("bob", "10.0.0.2", i * 60), db_session)

    # Now first "new" IP for each — Alice sees IP B for the first time, Bob sees IP A.
    alice_out = detector.check(_login("alice", "10.0.0.2", 240), db_session)
    bob_out = detector.check(_login("bob", "10.0.0.1", 240), db_session)
    assert len(alice_out) == 1 and "10.0.0.2" in alice_out[0].message
    assert len(bob_out) == 1 and "10.0.0.1" in bob_out[0].message


def test_non_login_events_ignored(db_session: Session) -> None:
    _ensure_user(db_session, "carol")
    detector = UnusualIpDetector()
    ev = make_event("carol", EventType.API_CALL, BASE, ip="10.0.0.55")
    assert detector.check(ev, db_session) == []
