"""Tests for time-based risk-score decay (app/scoring/decay_job.py).

Pure DB-session-in, dict-out — no scheduler or FastAPI app needs to be
running to exercise ``run_decay_pass`` directly, per its own design goal.

Anchors ("now") throughout are computed fresh via ``datetime.now(timezone.
utc)`` at each test's own execution time, NOT a hardcoded constant —
``run_decay_pass`` itself uses the real wall clock internally
(``datetime.now(timezone.utc)``), so a fixed constant would drift from
whatever the actual clock reads by the time the test runs, throwing off the
day-elapsed math these tests check to tight tolerances. The gap between a
test computing its own "now" and ``run_decay_pass`` computing its own
moments later is milliseconds — negligible against the day/month-scale
elapsed times under test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.behavior_profile import BehaviorProfile
from app.models.user import User
from app.scoring.decay_job import run_decay_pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_profile(
    db_session: Session,
    user_id: str,
    user_risk_score: float,
    updated_at: datetime | None,
) -> BehaviorProfile:
    """Insert a User + BehaviorProfile with an explicit (possibly backdated)
    ``updated_at``. Setting it directly on the constructor works even though
    the column has ``onupdate=func.now()`` — that trigger only fires on
    UPDATE statements, never on the initial INSERT, so whatever value is
    passed here is exactly what lands in the row.
    """
    now = _now()
    db_session.add(User(user_id=user_id, first_seen_at=now, last_seen_at=now))
    profile = BehaviorProfile(
        user_id=user_id,
        known_ips=[],
        deviation_score=0.0,
        user_risk_score=user_risk_score,
        last_event_at=now,
        updated_at=updated_at,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def test_no_decay_for_zero_risk_users(db_session: Session) -> None:
    """Profiles at user_risk_score == 0.0 are skipped entirely — not even
    touched/written. Proven by checking updated_at is untouched (still the
    explicit backdated value we set, not bumped by an UPDATE)."""
    old_ts = _now() - timedelta(days=100)
    profile = _seed_profile(db_session, "quiet_user", user_risk_score=0.0, updated_at=old_ts)

    summary = run_decay_pass(db_session, get_settings())

    assert summary["profiles_processed"] == 0
    assert summary["profiles_decayed"] == 0
    assert summary["total_score_removed"] == 0.0

    db_session.refresh(profile)
    assert profile.user_risk_score == 0.0
    assert profile.updated_at == old_ts.replace(tzinfo=None)  # never written


def test_decay_reduces_score_after_elapsed_time(db_session: Session) -> None:
    """30 days backdated, score 50.0 → decayed per the documented formula."""
    settings = get_settings()
    thirty_days_ago = _now() - timedelta(days=30)
    profile = _seed_profile(db_session, "alice", user_risk_score=50.0, updated_at=thirty_days_ago)

    summary = run_decay_pass(db_session, settings)

    expected = 50.0 * (settings.DAILY_DECAY_RATE**30.0)
    db_session.refresh(profile)

    assert profile.user_risk_score == pytest.approx(expected, rel=1e-4)
    assert profile.user_risk_score < 50.0
    # Sanity check against the documented default rate (0.98):
    # 0.98**30 ≈ 0.545, so 30 days should reduce the score by roughly 45% —
    # a real, visible drop, but nowhere near wiping it out entirely.
    assert 20.0 < profile.user_risk_score < 35.0

    assert summary["profiles_processed"] == 1
    assert summary["profiles_decayed"] == 1
    assert summary["total_score_removed"] == pytest.approx(50.0 - expected, rel=1e-4)


def test_minimal_decay_for_recently_updated_profile(db_session: Session) -> None:
    """D2's central interaction test: a profile touched moments ago (e.g. by
    a fresh per-event decay from a new alert) should see negligible decay
    from this job — the nightly/on-demand pass isn't meant to double-decay
    the same day's per-event contribution.
    """
    settings = get_settings()
    just_now = _now() - timedelta(minutes=5)
    profile = _seed_profile(db_session, "bob", user_risk_score=50.0, updated_at=just_now)

    summary = run_decay_pass(db_session, settings)

    db_session.refresh(profile)
    assert summary["profiles_processed"] == 1
    # ~5 minutes against a rate that halves in ~34 days: the drop must be a
    # tiny fraction of a point, not a meaningful chunk.
    assert profile.user_risk_score == pytest.approx(50.0, abs=0.05)
    assert profile.user_risk_score < 50.0  # some decay did happen, just negligible


def test_score_clamps_to_zero_below_floor(db_session: Session) -> None:
    """A very old, very small score decays to exactly 0.0, not a tiny
    non-zero remainder that would sit there forever."""
    settings = get_settings()
    ancient = _now() - timedelta(days=3650)  # ~10 years
    profile = _seed_profile(db_session, "stale_user", user_risk_score=0.05, updated_at=ancient)

    summary = run_decay_pass(db_session, settings)

    db_session.refresh(profile)
    assert profile.user_risk_score == 0.0
    assert summary["profiles_decayed"] == 1
    assert summary["total_score_removed"] == pytest.approx(0.05)


def test_returns_correct_summary(db_session: Session) -> None:
    """Multiple profiles in varying states → correct aggregate counts."""
    settings = get_settings()
    now = _now()
    _seed_profile(db_session, "zero", user_risk_score=0.0, updated_at=now - timedelta(days=50))
    _seed_profile(
        db_session, "below_floor", user_risk_score=0.005, updated_at=now - timedelta(days=50)
    )
    p1 = _seed_profile(db_session, "old1", user_risk_score=40.0, updated_at=now - timedelta(days=20))
    p2 = _seed_profile(db_session, "old2", user_risk_score=60.0, updated_at=now - timedelta(days=10))

    summary = run_decay_pass(db_session, settings)

    # zero and below_floor are both <= DECAY_SCORE_FLOOR (0.01) and never
    # queried/processed at all.
    assert summary["profiles_processed"] == 2
    assert summary["profiles_decayed"] == 2

    expected1 = 40.0 * (settings.DAILY_DECAY_RATE**20.0)
    expected2 = 60.0 * (settings.DAILY_DECAY_RATE**10.0)
    expected_total_removed = (40.0 - expected1) + (60.0 - expected2)

    assert summary["total_score_removed"] == pytest.approx(expected_total_removed, rel=1e-4)

    db_session.refresh(p1)
    db_session.refresh(p2)
    assert p1.user_risk_score == pytest.approx(expected1, rel=1e-4)
    assert p2.user_risk_score == pytest.approx(expected2, rel=1e-4)


def test_repeated_frequent_decay_converges_correctly(db_session: Session) -> None:
    """Proves the D2 reasoning with real numbers, not just an assertion.

    Exponential decay composes exactly under repeated multiplication of the
    same rate over sub-intervals: rate**(t1+t2) == rate**t1 * rate**t2. So
    ten decay passes one (elapsed) day apart each — simulating what actually
    happens in production, where each pass resets updated_at (the column's
    onupdate=func.now() fires on the UPDATE the pass triggers), and the next
    pass measures the elapsed time since — must land on the exact same score
    as one pass after an equivalent 10-day elapsed time on a fresh profile
    with the same starting score. If these diverged, the "run on startup +
    every 24h" schedule design would be subtly wrong; this test is the proof
    it isn't.

    Real wall-clock time obviously can't advance 10 days inside a test, so
    "one day apart" is simulated by explicitly backdating updated_at by one
    day before each pass — an explicit assignment always overrides
    onupdate's automatic "now" for that flush (onupdate only supplies a
    value when the column is otherwise unset), so this deterministically
    reproduces the elapsed-time input each scheduled run would actually see.
    """
    settings = get_settings()

    # -- Path A: one pass after 10 elapsed days. --
    profile_a = _seed_profile(
        db_session, "path_a", user_risk_score=50.0, updated_at=_now() - timedelta(days=10)
    )
    run_decay_pass(db_session, settings)
    db_session.refresh(profile_a)

    # -- Path B: ten passes, one simulated day apart each, same start. --
    profile_b = _seed_profile(
        db_session, "path_b", user_risk_score=50.0, updated_at=_now() - timedelta(days=1)
    )
    for _ in range(10):
        run_decay_pass(db_session, settings)
        db_session.refresh(profile_b)
        # Simulate "one more real day passes" before the next scheduled run.
        profile_b.updated_at = _now() - timedelta(days=1)
        db_session.add(profile_b)
        db_session.commit()
        db_session.refresh(profile_b)

    assert profile_a.user_risk_score == pytest.approx(profile_b.user_risk_score, rel=1e-4)

    # And both must equal the closed-form single-pass expectation.
    expected = 50.0 * (settings.DAILY_DECAY_RATE**10.0)
    assert profile_a.user_risk_score == pytest.approx(expected, rel=1e-4)
    assert profile_b.user_risk_score == pytest.approx(expected, rel=1e-4)
