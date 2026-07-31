"""Generic sliding-window container over LogEvent objects.

Eviction uses **event timestamps**, not wall-clock time — this is what makes
detectors deterministic and testable. Backed by a ``collections.deque`` for
amortised-O(1) append + left-pop.

Not thread-safe. Phase 3 assumes a single-process, single-worker uvicorn; a
Redis-backed replacement is a Phase 6+ concern for horizontal scaling.

Timestamps are captured at ``add()`` time and stored alongside the event, so
comparisons don't depend on later ORM refreshes (SQLite in particular strips
``tzinfo`` on reload, which would break naive/aware comparisons if we re-read
the attribute later). All timestamps are normalised to naive UTC for the
window's internal use.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.log_event import LogEvent


def _to_naive_utc(ts: datetime) -> datetime:
    """Convert an aware timestamp to naive UTC; leave naive timestamps alone."""
    if ts.tzinfo is None:
        return ts
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


class SlidingWindow:
    """Fixed-duration window over LogEvents, evicted by event timestamp."""

    def __init__(self, window_seconds: int) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = window_seconds
        # (naive-UTC timestamp snapshot, LogEvent) pairs. Snapshotting the
        # timestamp avoids depending on ORM refresh behaviour later.
        self._events: deque[tuple[datetime, LogEvent]] = deque()

    # ------------------------------------------------------------------ core

    def add(self, event: LogEvent) -> None:
        """Append the event, then evict anything older than the window."""
        ts = _to_naive_utc(event.timestamp)
        self._events.append((ts, event))
        self._evict(ts)

    def events_in_window(self, now: datetime | None = None) -> list[LogEvent]:
        """Return all events currently in the window.

        ``now`` anchors eviction. If ``None``, uses the timestamp of the most
        recent event (matching detector semantics — "as of the last event I
        saw"). If the window is empty, returns ``[]``.
        """
        if not self._events:
            return []
        anchor = _to_naive_utc(now) if now is not None else self._events[-1][0]
        self._evict(anchor)
        return [ev for _, ev in self._events]

    def count(self, predicate: Callable[[LogEvent], bool] | None = None) -> int:
        """Count events in the window, optionally filtered by ``predicate``."""
        if predicate is None:
            return len(self._events)
        return sum(1 for _, ev in self._events if predicate(ev))

    def distinct(self, key_fn: Callable[[LogEvent], Any]) -> set:
        """Return the set of distinct ``key_fn(event)`` values in the window."""
        return {key_fn(ev) for _, ev in self._events}

    def clear(self) -> None:
        """Drop all events."""
        self._events.clear()

    # -------------------------------------------------------------- internal

    def _evict(self, anchor: datetime) -> None:
        cutoff = anchor - timedelta(seconds=self.window_seconds)
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
