"""BruteForceDetector unit tests."""

from datetime import datetime, timedelta, timezone

from app.detection.rules.brute_force import BruteForceDetector
from app.schemas.common import EventType, Severity

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def _feed_failures(
    detector: BruteForceDetector,
    user_id: str,
    n: int,
    start: float = 0.0,
    step: float = 1.0,
) -> list:
    """Feed ``n`` LOGIN_FAILUREs and return the list-of-lists of candidates."""
    results = []
    for i in range(n):
        ev = make_event(
            user_id=user_id,
            event_type=EventType.LOGIN_FAILURE,
            timestamp=BASE + timedelta(seconds=start + i * step),
        )
        results.append(detector.check(ev, db=None))
    return results


def test_four_failures_no_candidates() -> None:
    d = BruteForceDetector()
    out = _feed_failures(d, "alice", 4)
    assert all(x == [] for x in out)


def test_fifth_failure_emits_medium_only_once() -> None:
    d = BruteForceDetector()
    out = _feed_failures(d, "alice", 5)

    # First four silent, the fifth is MEDIUM.
    assert all(x == [] for x in out[:4])
    assert len(out[4]) == 1
    assert out[4][0].severity == Severity.MEDIUM
    assert out[4][0].score == 45
    assert out[4][0].alert_type == "brute_force"


def test_no_new_alert_between_medium_and_high() -> None:
    d = BruteForceDetector()
    out = _feed_failures(d, "alice", 9)
    # 5th → MEDIUM, 6..9 → nothing.
    assert out[4] and out[4][0].severity == Severity.MEDIUM
    for i in (5, 6, 7, 8):
        assert out[i] == []


def test_tenth_failure_emits_high() -> None:
    d = BruteForceDetector()
    out = _feed_failures(d, "alice", 10)
    assert out[9] and out[9][0].severity == Severity.HIGH
    assert out[9][0].score == 70


def test_twentieth_failure_emits_critical() -> None:
    d = BruteForceDetector()
    out = _feed_failures(d, "alice", 25)

    # Only these three events emit anything.
    emitted = {i: cands for i, cands in enumerate(out) if cands}
    assert set(emitted.keys()) == {4, 9, 19}
    assert emitted[4][0].severity == Severity.MEDIUM
    assert emitted[9][0].severity == Severity.HIGH
    assert emitted[19][0].severity == Severity.CRITICAL
    assert emitted[19][0].score == 90


def test_success_after_failures_emits_brute_force_success() -> None:
    d = BruteForceDetector()
    _feed_failures(d, "alice", 5)  # triggers MEDIUM at index 4
    success = make_event(
        user_id="alice",
        event_type=EventType.LOGIN_SUCCESS,
        timestamp=BASE + timedelta(seconds=6),
    )
    cands = d.check(success, db=None)
    assert len(cands) == 1
    assert cands[0].alert_type == "brute_force_success"
    assert cands[0].severity == Severity.CRITICAL
    assert cands[0].score == 95
    assert "5" in cands[0].message


def test_failures_outside_window_do_not_accumulate() -> None:
    d = BruteForceDetector()
    # First failure at t=0, next at t=90 → outside 60s window.
    ev1 = make_event("alice", EventType.LOGIN_FAILURE, BASE)
    ev2 = make_event(
        "alice", EventType.LOGIN_FAILURE, BASE + timedelta(seconds=90)
    )
    assert d.check(ev1, db=None) == []
    assert d.check(ev2, db=None) == []


def test_users_tracked_independently() -> None:
    d = BruteForceDetector()
    # Alice hits threshold, Bob does not.
    out_alice = _feed_failures(d, "alice", 5)
    out_bob = _feed_failures(d, "bob", 3, start=100)

    assert out_alice[4] and out_alice[4][0].severity == Severity.MEDIUM
    assert all(x == [] for x in out_bob)


def test_success_without_failures_emits_nothing() -> None:
    d = BruteForceDetector()
    success = make_event("alice", EventType.LOGIN_SUCCESS, BASE)
    assert d.check(success, db=None) == []
