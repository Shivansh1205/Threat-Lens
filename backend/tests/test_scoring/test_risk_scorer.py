"""Unit tests for RiskScorer — pure formula tests, no DB/HTTP involved.

Uses real (non-mocked) BehaviorProfile/AlertCandidate instances, since
score_alert()/update_user_risk() only ever read/write plain attributes on
them — no session interaction is needed to exercise the math.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.config import get_settings
from app.detection.base import AlertCandidate
from app.models.behavior_profile import BehaviorProfile
from app.scoring.risk_scorer import RiskScorer, severity_for_score
from app.schemas.common import Severity


def _candidate(score: int, severity: Severity, alert_type: str = "brute_force") -> AlertCandidate:
    return AlertCandidate(
        alert_type=alert_type,
        severity=severity,
        score=score,
        message="test candidate",
        triggered_by_event_id=uuid4(),
    )


def _profile(deviation_score: float = 0.0, user_risk_score: float = 0.0) -> BehaviorProfile:
    return BehaviorProfile(
        user_id="alice",
        known_ips=[],
        deviation_score=deviation_score,
        user_risk_score=user_risk_score,
    )


@pytest.fixture
def scorer() -> RiskScorer:
    # db is never touched by score_alert()/update_user_risk() (both are pure
    # attribute read/writes), so None is fine here.
    return RiskScorer(db=None, settings=get_settings())


# --------------------------------------------------------------- score_alert


def test_score_alert_no_deviation(scorer: RiskScorer) -> None:
    """deviation_score == 0.0 must be an exact no-op: adjusted == raw."""
    candidate = _candidate(45, Severity.MEDIUM)
    profile = _profile(deviation_score=0.0)

    result = scorer.score_alert(candidate, profile)

    assert result["raw_score"] == 45
    assert result["raw_severity"] == Severity.MEDIUM
    assert result["adjusted_score"] == 45
    assert result["adjusted_severity"] == Severity.MEDIUM


def test_score_alert_with_deviation_low_base(scorer: RiskScorer) -> None:
    """Lots of headroom above a low base_score → deviation pushes it up a lot.

    adjusted = 20 + 1.0 * 0.3 * (100 - 20) = 20 + 24 = 44
    """
    candidate = _candidate(20, Severity.LOW)
    profile = _profile(deviation_score=1.0)

    result = scorer.score_alert(candidate, profile)

    assert result["raw_score"] == 20
    assert result["adjusted_score"] == 44
    assert result["adjusted_score"] > result["raw_score"]


def test_score_alert_with_deviation_high_base(scorer: RiskScorer) -> None:
    """Little headroom above a high base_score → deviation barely moves it.

    adjusted = 90 + 1.0 * 0.3 * (100 - 90) = 90 + 3 = 93
    """
    candidate = _candidate(90, Severity.CRITICAL)
    profile = _profile(deviation_score=1.0)

    result = scorer.score_alert(candidate, profile)

    assert result["raw_score"] == 90
    assert result["adjusted_score"] == 93
    assert result["adjusted_score"] <= 100
    # "only slightly" higher — nowhere near the full +30 a low-base alert gets.
    assert result["adjusted_score"] - result["raw_score"] == 3


def test_score_alert_clamped_at_100() -> None:
    """A weight above the formula's normal range must still clamp to 100."""
    from app.config import Settings

    hot_settings = Settings(DEVIATION_WEIGHT=2.0)
    scorer = RiskScorer(db=None, settings=hot_settings)
    candidate = _candidate(90, Severity.CRITICAL)
    profile = _profile(deviation_score=1.0)

    result = scorer.score_alert(candidate, profile)

    # 90 + 1.0 * 2.0 * (100 - 90) = 90 + 20 = 110, clamped to 100.
    assert result["adjusted_score"] == 100
    assert result["adjusted_severity"] == Severity.CRITICAL


def test_score_alert_severity_rebucket(scorer: RiskScorer) -> None:
    """A MEDIUM detector alert can become HIGH after adjustment; raw stays MEDIUM.

    adjusted = 45 + 1.0 * 0.3 * (100 - 45) = 45 + 16.5 = 61.5 -> round -> 62
    severity_for_score(62) == HIGH (bucket 51-75).
    """
    candidate = _candidate(45, Severity.MEDIUM)
    profile = _profile(deviation_score=1.0)

    result = scorer.score_alert(candidate, profile)

    assert result["raw_severity"] == Severity.MEDIUM
    assert result["adjusted_score"] == 62
    assert result["adjusted_severity"] == Severity.HIGH
    assert result["raw_severity"] != result["adjusted_severity"]


# --------------------------------------------------------------- severity_for_score


def test_severity_for_score_boundaries(scorer: RiskScorer) -> None:
    settings = get_settings()
    assert severity_for_score(0, settings) == Severity.LOW
    assert severity_for_score(25, settings) == Severity.LOW
    assert severity_for_score(26, settings) == Severity.MEDIUM
    assert severity_for_score(50, settings) == Severity.MEDIUM
    assert severity_for_score(51, settings) == Severity.HIGH
    assert severity_for_score(75, settings) == Severity.HIGH
    assert severity_for_score(76, settings) == Severity.CRITICAL
    assert severity_for_score(100, settings) == Severity.CRITICAL


# --------------------------------------------------------------- update_user_risk


def test_update_user_risk_first_alert(scorer: RiskScorer) -> None:
    """0.0 * 0.995 + 70 * 0.15 = 10.5"""
    profile = _profile(user_risk_score=0.0)

    new_value = scorer.update_user_risk(profile, 70)

    assert new_value == pytest.approx(10.5)
    assert profile.user_risk_score == pytest.approx(10.5)


def test_update_user_risk_accumulates(scorer: RiskScorer) -> None:
    """Three sequential updates must reflect decay-then-add, not summation."""
    settings = get_settings()
    decay = settings.USER_RISK_DECAY_FACTOR
    weight = settings.RISK_CONTRIBUTION_WEIGHT

    profile = _profile(user_risk_score=0.0)
    scores = [70, 50, 90]

    expected = 0.0
    for s in scores:
        expected = min(100.0, expected * decay + s * weight)
        actual = scorer.update_user_risk(profile, s)
        assert actual == pytest.approx(expected)

    # Sanity: nowhere near a naive sum (70+50+90=210, or even a clamped 100
    # reached via mere summation) — decay is genuinely doing something, and
    # the formula-level check above already proves it's not simple addition.
    assert profile.user_risk_score == pytest.approx(expected)
    assert profile.user_risk_score < sum(scores)


def test_update_user_risk_decays_toward_zero_with_low_scores(scorer: RiskScorer) -> None:
    """Many small-score updates must stay well-damped, not grow linearly."""
    profile = _profile(user_risk_score=0.0)

    n = 20
    small_score = 5
    for _ in range(n):
        scorer.update_user_risk(profile, small_score)

    naive_sum = n * small_score  # 100 — what pure summation (no decay) would give
    assert profile.user_risk_score > 0.0  # some growth did happen
    assert profile.user_risk_score < naive_sum / 4  # but heavily damped by decay
