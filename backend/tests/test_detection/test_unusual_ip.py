"""UnusualIpDetector unit tests."""

from datetime import datetime, timedelta, timezone

from app.detection.rules.unusual_ip import UnusualIpDetector
from app.schemas.common import EventType, Severity

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def _login(user_id: str, ip: str, t: float, event_type: EventType = EventType.LOGIN_SUCCESS):
    return make_event(user_id, event_type, BASE + timedelta(seconds=t), ip=ip)


def test_bootstrap_first_three_logins_no_candidates() -> None:
    d = UnusualIpDetector()
    outs = [d.check(_login("carol", "10.0.0.1", i * 60), db=None) for i in range(3)]
    assert all(x == [] for x in outs)


def test_fourth_login_from_known_ip_no_candidate() -> None:
    d = UnusualIpDetector()
    for i in range(3):
        d.check(_login("carol", "10.0.0.1", i * 60), db=None)
    out = d.check(_login("carol", "10.0.0.1", 240), db=None)
    assert out == []


def test_fourth_login_from_new_ip_emits_low() -> None:
    d = UnusualIpDetector()
    for i in range(3):
        d.check(_login("carol", "10.0.0.1", i * 60), db=None)
    out = d.check(_login("carol", "10.0.0.99", 240), db=None)
    assert len(out) == 1
    assert out[0].alert_type == "unusual_ip"
    assert out[0].severity == Severity.LOW
    assert out[0].score == 30
    assert "10.0.0.99" in out[0].message


def test_second_login_from_new_ip_not_reflagged() -> None:
    d = UnusualIpDetector()
    for i in range(3):
        d.check(_login("carol", "10.0.0.1", i * 60), db=None)
    first = d.check(_login("carol", "10.0.0.99", 240), db=None)
    second = d.check(_login("carol", "10.0.0.99", 300), db=None)
    assert len(first) == 1
    assert second == []


def test_users_tracked_independently() -> None:
    d = UnusualIpDetector()
    # Alice bootstraps on IP A, Bob bootstraps on IP B. Their known-sets don't leak.
    for i in range(3):
        d.check(_login("alice", "10.0.0.1", i * 60), db=None)
        d.check(_login("bob", "10.0.0.2", i * 60), db=None)

    # Now first "new" IP for each — Alice sees IP B for the first time, Bob sees IP A.
    alice_out = d.check(_login("alice", "10.0.0.2", 240), db=None)
    bob_out = d.check(_login("bob", "10.0.0.1", 240), db=None)
    assert len(alice_out) == 1 and "10.0.0.2" in alice_out[0].message
    assert len(bob_out) == 1 and "10.0.0.1" in bob_out[0].message


def test_non_login_events_ignored() -> None:
    d = UnusualIpDetector()
    ev = make_event("carol", EventType.API_CALL, BASE, ip="10.0.0.55")
    assert d.check(ev, db=None) == []
