"""Port-scan detector.

Fires when a single source IP touches many *distinct* ports in a short
window (HIGH at 15+, CRITICAL at 50+). Repeated access to the *same* port
doesn't count — the whole point of a scan is breadth. Emits one candidate per
event, at the highest new threshold that call crossed.

Thread-safety: same situation as BruteForceDetector (see its module
docstring) — ``check()`` runs on Starlette's threadpool against one shared
detector instance for the whole process. A single ``threading.Lock`` guards
the read-decide-write section per call.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.detection.base import AlertCandidate, Detector
from app.models.log_event import LogEvent
from app.schemas.common import EventType, Severity


def _to_naive_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


class _PortSnap:
    """Plain-value snapshot extracted from a LogEvent at observation time.

    Never holds an ORM reference, so it stays valid across session commits.
    """

    __slots__ = ("ts", "port", "event_id", "ip")

    def __init__(self, event: LogEvent) -> None:
        self.ts: datetime = _to_naive_utc(event.timestamp)
        self.port: int = event.port  # type: ignore[assignment]
        self.event_id: UUID = event.id
        self.ip: str = event.ip


class PortScanDetector(Detector):
    """Per-IP distinct-port-rate detector."""

    def __init__(self) -> None:
        # TODO(Phase 6+): move to Redis for horizontal scaling.
        self._windows: dict[str, deque[_PortSnap]] = {}
        self._last_emitted: dict[str, int] = {}
        self._settings = get_settings()
        # One global lock for this detector instance — see BruteForceDetector's
        # module docstring for why a global lock (vs. per-key) is the right
        # call here.
        self._lock = threading.Lock()

    def check(self, event: LogEvent, db: Session) -> list[AlertCandidate]:
        if event.event_type != EventType.PORT_ACCESS:
            return []
        # A PORT_ACCESS event without a port is ambiguous — ignore it rather than
        # counting it as a "distinct None" entry.
        if event.port is None:
            return []

        s = self._settings
        snap = _PortSnap(event)  # snapshot all needed values before any commit

        # Locked for the whole read-decide-write sequence: window mutation,
        # distinct-count read, and the last_emitted threshold check/update
        # all need to happen atomically with respect to other threads.
        with self._lock:
            window = self._windows.setdefault(event.ip, deque())
            window.append(snap)
            self._evict(window, snap.ts, s.PORT_SCAN_WINDOW_SECONDS)

            distinct = len({sn.port for sn in window})
            last = self._last_emitted.get(event.ip, 0)

            if (
                distinct >= s.PORT_SCAN_CRITICAL_THRESHOLD
                and last < s.PORT_SCAN_CRITICAL_THRESHOLD
            ):
                self._last_emitted[event.ip] = s.PORT_SCAN_CRITICAL_THRESHOLD
                return [self._candidate(snap, Severity.CRITICAL, 95, distinct)]
            if distinct >= s.PORT_SCAN_HIGH_THRESHOLD and last < s.PORT_SCAN_HIGH_THRESHOLD:
                self._last_emitted[event.ip] = s.PORT_SCAN_HIGH_THRESHOLD
                return [self._candidate(snap, Severity.HIGH, 75, distinct)]

            return []

    @staticmethod
    def _evict(window: deque[_PortSnap], anchor: datetime, window_seconds: int) -> None:
        cutoff = anchor - timedelta(seconds=window_seconds)
        while window and window[0].ts < cutoff:
            window.popleft()

    @staticmethod
    def _candidate(snap: _PortSnap, severity: Severity, score: int, distinct: int) -> AlertCandidate:
        return AlertCandidate(
            alert_type="port_scan",
            severity=severity,
            score=score,
            message=(
                f"{distinct} distinct ports probed from {snap.ip} within the "
                "sliding window."
            ),
            triggered_by_event_id=snap.event_id,
        )
