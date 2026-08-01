"""Detector registry — the only place that persists alerts.

Detectors are pure and stateless-with-respect-to-the-DB. The registry runs each
detector against an event, collects the ``AlertCandidate``s they emit, scores
each one with ``RiskScorer`` against the user's ``BehaviorProfile``, and
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
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent
from app.scoring.risk_scorer import RiskScorer


class DetectorRegistry:
    """Runs a fixed list of detectors, scores their output, and persists it."""

    def __init__(self, detectors: list[Detector]) -> None:
        self.detectors = detectors

    def run_all(self, event: LogEvent, db: Session, profile: BehaviorProfile) -> list[Alert]:
        """Run every detector, then risk-score and persist whatever fires.

        ``profile`` must reflect the user's behavioral state as of *this*
        event — specifically, ``profile.deviation_score`` should already be
        computed for the current event (see api/logs.py's ingestion-order
        comment for why this means calling
        ``BehaviorProfiler.compute_deviation()`` before this method, ahead of
        the rest of ``BehaviorProfiler.update()``'s mutations).

        Each candidate is scored independently via ``RiskScorer.score_alert``,
        and contributes once to ``profile.user_risk_score`` via
        ``RiskScorer.update_user_risk`` — if one event produces multiple
        alerts, the rolling risk score is updated once per alert, not once
        per event.
        """
        candidates: list[AlertCandidate] = []
        for detector in self.detectors:
            candidates.extend(detector.check(event, db))

        if not candidates:
            return []

        scorer = RiskScorer(db)
        alerts: list[Alert] = []
        for c in candidates:
            result = scorer.score_alert(c, profile)
            scorer.update_user_risk(profile, result["adjusted_score"])
            alerts.append(
                Alert(
                    user_id=event.user_id,
                    alert_type=c.alert_type,
                    severity=result["adjusted_severity"],
                    score=result["adjusted_score"],
                    raw_severity=result["raw_severity"],
                    raw_score=result["raw_score"],
                    message=c.message,
                    triggered_by_event_id=c.triggered_by_event_id,
                )
            )

        db.add_all(alerts)
        db.add(profile)
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
