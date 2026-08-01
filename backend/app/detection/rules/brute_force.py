"""Brute-force login detector.

Fires on repeated ``LOGIN_FAILURE`` events for the same ``user_id`` within a
configurable sliding window, escalating in severity as the failure count
crosses the MEDIUM/HIGH/CRITICAL thresholds. Emits *one* candidate per event —
the highest new threshold that call crossed. If a ``LOGIN_SUCCESS`` arrives
while a burst of failures is still in the window, emits a separate
CRITICAL ``brute_force_success`` candidate (the "attack succeeded" signal) and
clears the state.

Thread-safety: ``check()`` is called from Starlette's threadpool — FastAPI
runs this (sync) endpoint's request handling on worker threads, and
``DetectorRegistry`` holds one shared instance of this detector for the whole
process (see registry.py). Without synchronization, two concurrent requests
for the same user_id can both read ``last_emitted`` before either writes it,
producing duplicate alerts at the same threshold (or worse: interleaved
writes to the same SlidingWindow's deque corrupting the count). A single
``threading.Lock`` around the whole read-decide-write section in ``check()``
fixes this — see the lock discussion below.
"""

from __future__ import annotations

import threading

from sqlalchemy.orm import Session

from app.config import get_settings
from app.detection.base import AlertCandidate, Detector
from app.detection.sliding_window import SlidingWindow
from app.models.log_event import LogEvent
from app.schemas.common import EventType, Severity


class BruteForceDetector(Detector):
    """Per-user failed-login rate detector."""

    def __init__(self) -> None:
        # TODO(Phase 6+): move to Redis for horizontal scaling.
        self._windows: dict[str, SlidingWindow] = {}
        self._last_emitted: dict[str, int] = {}
        self._settings = get_settings()
        # One global lock for this detector instance, not one lock per
        # user_id. Simpler and correct: check() does a handful of dict/deque
        # operations per call (no I/O, no DB access — db is unused here), so
        # serializing all calls to this detector process-wide is not a
        # meaningful bottleneck at this project's scale. A per-key locking
        # scheme (e.g. a dict of locks keyed by user_id) would let different
        # users' requests run fully in parallel, but adds real complexity
        # (locks-for-locks bookkeeping, cleanup of stale per-key locks) for a
        # win that doesn't matter until this is under far heavier load than
        # a demo/coursework deployment sees.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ core

    def check(self, event: LogEvent, db: Session) -> list[AlertCandidate]:
        # Locked for the whole dispatch: both _on_failure and _on_success read
        # and mutate self._windows / self._last_emitted, and must do so
        # atomically with respect to other threads calling check() for the
        # same (or a different) user_id.
        with self._lock:
            if event.event_type == EventType.LOGIN_FAILURE:
                return self._on_failure(event)
            if event.event_type == EventType.LOGIN_SUCCESS:
                return self._on_success(event)
            return []

    # -------------------------------------------------------------- handlers

    def _on_failure(self, event: LogEvent) -> list[AlertCandidate]:
        s = self._settings
        window = self._windows.setdefault(
            event.user_id, SlidingWindow(s.BRUTE_FORCE_WINDOW_SECONDS)
        )
        window.add(event)
        count = window.count()
        last = self._last_emitted.get(event.user_id, 0)

        # Emit the highest *new* threshold this event crossed, once.
        if count >= s.BRUTE_FORCE_CRITICAL_THRESHOLD and last < s.BRUTE_FORCE_CRITICAL_THRESHOLD:
            self._last_emitted[event.user_id] = s.BRUTE_FORCE_CRITICAL_THRESHOLD
            return [self._candidate(event, Severity.CRITICAL, 90, count)]
        if count >= s.BRUTE_FORCE_HIGH_THRESHOLD and last < s.BRUTE_FORCE_HIGH_THRESHOLD:
            self._last_emitted[event.user_id] = s.BRUTE_FORCE_HIGH_THRESHOLD
            return [self._candidate(event, Severity.HIGH, 70, count)]
        if count >= s.BRUTE_FORCE_MEDIUM_THRESHOLD and last < s.BRUTE_FORCE_MEDIUM_THRESHOLD:
            self._last_emitted[event.user_id] = s.BRUTE_FORCE_MEDIUM_THRESHOLD
            return [self._candidate(event, Severity.MEDIUM, 45, count)]

        return []

    def _on_success(self, event: LogEvent) -> list[AlertCandidate]:
        s = self._settings
        window = self._windows.get(event.user_id)
        if window is None:
            return []

        # Anchor eviction to the success timestamp so long-past failures don't count.
        active_failures = len(window.events_in_window(now=event.timestamp))

        candidates: list[AlertCandidate] = []
        if active_failures >= s.BRUTE_FORCE_MEDIUM_THRESHOLD:
            candidates.append(
                AlertCandidate(
                    alert_type="brute_force_success",
                    severity=Severity.CRITICAL,
                    score=95,
                    message=(
                        f"Successful login for {event.user_id} after "
                        f"{active_failures} failed attempts within "
                        f"{s.BRUTE_FORCE_WINDOW_SECONDS}s — likely compromise."
                    ),
                    triggered_by_event_id=event.id,
                )
            )

        # Success wipes brute-force state either way.
        window.clear()
        self._last_emitted.pop(event.user_id, None)

        return candidates

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _candidate(
        event: LogEvent, severity: Severity, score: int, count: int
    ) -> AlertCandidate:
        return AlertCandidate(
            alert_type="brute_force",
            severity=severity,
            score=score,
            message=(
                f"{count} failed logins for {event.user_id} within the sliding window."
            ),
            triggered_by_event_id=event.id,
        )
