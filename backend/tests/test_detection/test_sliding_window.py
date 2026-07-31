"""Sliding window unit tests."""

from datetime import datetime, timedelta, timezone

from app.detection.sliding_window import SlidingWindow
from app.schemas.common import EventType

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def _ev(offset_seconds: float, ip: str = "10.0.0.1"):
    return make_event(
        user_id="alice",
        event_type=EventType.API_CALL,
        timestamp=BASE + timedelta(seconds=offset_seconds),
        ip=ip,
    )


def test_add_five_events_within_window_counts_five() -> None:
    w = SlidingWindow(window_seconds=10)
    for i in range(5):
        w.add(_ev(i))
    assert w.count() == 5


def test_events_outside_window_are_evicted() -> None:
    w = SlidingWindow(window_seconds=10)
    for i in range(5):
        w.add(_ev(i))
    # Jump well past the window; only this last event survives.
    w.add(_ev(15))
    assert w.count() == 1


def test_predicate_filtering() -> None:
    w = SlidingWindow(window_seconds=10)
    for i in range(5):
        w.add(_ev(i))
    # Even-offset events: 0, 2, 4 → 3 of them.
    even_count = w.count(
        predicate=lambda e: int((e.timestamp - BASE).total_seconds()) % 2 == 0
    )
    assert even_count == 3


def test_distinct_returns_unique_key_set() -> None:
    w = SlidingWindow(window_seconds=10)
    # 5 events but only 3 unique IPs.
    for i, ip in enumerate(["a", "a", "b", "c", "c"]):
        w.add(_ev(i, ip=ip))
    assert w.distinct(lambda e: e.ip) == {"a", "b", "c"}


def test_clear_empties_window() -> None:
    w = SlidingWindow(window_seconds=10)
    w.add(_ev(0))
    w.add(_ev(1))
    w.clear()
    assert w.count() == 0
    assert w.events_in_window() == []
