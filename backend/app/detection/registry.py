"""Detector registry — the only place that persists alerts.

Detectors are pure and stateless-with-respect-to-the-DB. The registry runs each
detector against an event, collects the ``AlertCandidate``s they emit, and
materialises them as ``Alert`` rows in a single flush + commit.

The module holds a lazy singleton because detector state (sliding windows,
known-IP sets) is per-process. Tests call ``reset_registry()`` in a fixture to
isolate state between test cases.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.detection.base import AlertCandidate, Detector
from app.detection.rules import BruteForceDetector, PortScanDetector, UnusualIpDetector
from app.models.alert import Alert
from app.models.log_event import LogEvent


class DetectorRegistry:
    """Runs a fixed list of detectors and persists their candidates."""

    def __init__(self, detectors: list[Detector]) -> None:
        self.detectors = detectors

    def run_all(self, event: LogEvent, db: Session) -> list[Alert]:
        candidates: list[AlertCandidate] = []
        for detector in self.detectors:
            candidates.extend(detector.check(event, db))

        if not candidates:
            return []

        alerts = [
            Alert(
                user_id=event.user_id,
                alert_type=c.alert_type,
                severity=c.severity,
                score=c.score,
                message=c.message,
                triggered_by_event_id=c.triggered_by_event_id,
            )
            for c in candidates
        ]
        db.add_all(alerts)
        db.flush()
        return alerts


# ------------------------------------------------------------------ singleton

_registry: DetectorRegistry | None = None


def get_registry() -> DetectorRegistry:
    """Lazily construct the process-wide registry."""
    global _registry
    if _registry is None:
        _registry = DetectorRegistry(
            [
                BruteForceDetector(),
                PortScanDetector(),
                UnusualIpDetector(),
            ]
        )
    return _registry


def reset_registry() -> None:
    """For tests: drop the cached registry so the next ``get_registry()`` call
    builds a fresh one with empty detector state.
    """
    global _registry
    _registry = None
