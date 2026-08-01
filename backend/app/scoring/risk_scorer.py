"""Dynamic risk scoring — combines a detector's raw severity/score with the
user's behavioral context to produce a final, context-aware alert score, and
maintains a rolling per-user risk score across every alert they trigger.

Two distinct scores live in this system. Do not conflate them (see
PHASES.md's Phase 4 "Dynamic risk scoring" section and ARCHITECTURE.md's
Scoring layer for the design rationale):

1. EVENT/ALERT RISK SCORE (0-100, per alert) — "how dangerous is THIS alert,
   right now, given what we know about this user?" ``score_alert()`` below.
   Pure function: takes a detector's ``AlertCandidate`` and the user's
   ``BehaviorProfile``, returns the raw and adjusted score/severity. Does not
   mutate either argument or touch the DB.

2. USER RISK SCORE (0-100, per user, rolling over time) — "how concerning is
   this user's PATTERN of behavior, cumulatively, right now?"
   ``update_user_risk()`` below. Lives on ``BehaviorProfile.user_risk_score``,
   mutated in place once per alert (caller commits). This is what backs
   ``GET /api/v1/users/high-risk``.

   IMPORTANT — decay is per-alert-event, not per-elapsed-time. A "proper"
   decay would shrink a user's rolling risk once per elapsed day even if they
   trigger no new alerts, which needs a scheduled/background job. That
   infrastructure doesn't exist yet, so for now the decay factor is applied
   once each time a NEW alert arrives for that user — a user who triggers
   nothing keeps whatever score they last had, forever, until (or unless) a
   scheduled job is added. See PHASES.md for this documented as a named
   Phase 5.5/6+ follow-up. Do not mistake this for real-time decay.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.detection.base import AlertCandidate
from app.models.behavior_profile import BehaviorProfile
from app.schemas.common import Severity


def severity_for_score(score: int, settings: Settings | None = None) -> Severity:
    """Bucket a 0-100 score into a Severity using the boundaries in config.

    Single source of truth for score -> severity bucketing (LOW 0-25 /
    MEDIUM 26-50 / HIGH 51-75 / CRITICAL 76-100 by default). Detectors still
    assign their own literal ``Severity`` today for their raw candidates
    (their score constants were chosen to already land in the matching
    bucket — see rules/*.py), but ``RiskScorer`` is what actually needs to
    re-derive severity after adjustment, since the adjusted score can cross
    a bucket boundary the detector never considered.
    """
    s = settings or get_settings()
    if score <= s.SEVERITY_LOW_MAX:
        return Severity.LOW
    if score <= s.SEVERITY_MEDIUM_MAX:
        return Severity.MEDIUM
    if score <= s.SEVERITY_HIGH_MAX:
        return Severity.HIGH
    return Severity.CRITICAL


class RiskScorer:
    """Adjusts alert scores using behavioral context, and maintains each
    user's rolling risk score.
    """

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # ------------------------------------------------------------- per-alert

    def score_alert(self, candidate: AlertCandidate, profile: BehaviorProfile) -> dict:
        """Combine a detector's raw score with the user's deviation_score.

        Pure — reads ``candidate``/``profile``, returns a dict, mutates
        neither and does not touch the DB.

            adjusted = base + deviation * DEVIATION_WEIGHT * (100 - base)

        The ``(100 - base)`` term is deliberate headroom scaling: a
        high-severity base score has little room left to climb, so
        behavioral novelty alone can't catapult a low-severity alert
        straight to CRITICAL — but it can still meaningfully escalate a
        borderline MEDIUM/HIGH alert when the surrounding context is
        unusual. At deviation_score == 0.0 this is an exact identity
        (adjusted == base), by construction — see
        test_score_alert_no_deviation.

        Clamped to [0, 100] and rounded to the nearest int before being
        re-bucketed into a (possibly different) severity.
        """
        base_score = candidate.score
        deviation = profile.deviation_score or 0.0

        raw_adjusted = base_score + deviation * self.settings.DEVIATION_WEIGHT * (100 - base_score)
        adjusted_score = round(max(0.0, min(100.0, raw_adjusted)))

        return {
            "raw_score": base_score,
            "raw_severity": candidate.severity,
            "adjusted_score": adjusted_score,
            "adjusted_severity": severity_for_score(adjusted_score, self.settings),
        }

    # -------------------------------------------------------- rolling risk

    def update_user_risk(self, profile: BehaviorProfile, adjusted_score: int) -> float:
        """Roll one alert's adjusted score into the user's cumulative risk.

            new = min(100, profile.user_risk_score * DECAY_FACTOR
                            + adjusted_score * RISK_CONTRIBUTION_WEIGHT)

        Mutates ``profile.user_risk_score`` in place; the caller is
        responsible for committing. If multiple alerts fire from a single
        event, call this once per alert (not once per event) — each alert is
        its own contribution to the rolling score.

        See this module's docstring for why decay is per-alert-event rather
        than per-elapsed-time in this phase.
        """
        s = self.settings
        current = profile.user_risk_score or 0.0
        new_value = min(100.0, current * s.USER_RISK_DECAY_FACTOR + adjusted_score * s.RISK_CONTRIBUTION_WEIGHT)
        profile.user_risk_score = new_value
        return new_value
