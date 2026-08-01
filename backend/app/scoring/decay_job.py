"""Time-based decay for ``BehaviorProfile.user_risk_score``.

This is the scheduled counterpart to ``RiskScorer.update_user_risk()``'s
per-alert-event decay (see risk_scorer.py's module docstring). That decay
only fires when a user triggers a NEW alert — a user who was flagged once
and then behaves perfectly for months never sees their score fall, because
nothing re-triggers it. This module closes that gap with genuine wall-clock
decay, independent of new events, run by a scheduled job (see main.py's
lifespan handler) and exposed for manual triggering via
``POST /api/v1/admin/decay-now`` (see api/admin.py).

FORMULA — exponential decay compounded over actual elapsed days, not a flat
per-run multiply:

    days_elapsed = (now - anchor).total_seconds() / 86400.0
    decayed = score * (DAILY_DECAY_RATE ** days_elapsed)

using real elapsed time (not "one run = one day") matters because the job
might not run exactly every 24h — server downtime, a missed run, a demo
restart — so decay has to reflect how much time actually passed, not how
many times the job happened to fire.

WHY ``updated_at`` AS THE ANCHOR IS SAFE UNDER REPEATED/FREQUENT RUNS
(worked through with real numbers, not just asserted): ``updated_at`` has
``onupdate=func.now()`` (see models/behavior_profile.py), so it resets to
"now" every time this job actually decays a profile — including on the very
next run. Does that make frequent decay passes wrong? No: exponential decay
composes exactly under repeated multiplication of the same rate over
sub-intervals, because ``rate**(t1 + t2) == rate**t1 * rate**t2``. Concretely,
for a starting score of 50.0 and DAILY_DECAY_RATE=0.98:

    (a) one pass after 10 elapsed days:
        50.0 * (0.98 ** 10) ≈ 40.86

    (b) ten passes, one (real, elapsed) day apart each — which is what
        actually happens in production with the 24h scheduler, since each
        run resets updated_at and the next run measures the 1.0 days since:
        50.0 * (0.98 ** 1) ** 10 == 50.0 * (0.98 ** 10) ≈ 40.86

(a) and (b) are the SAME value, not approximately — algebraically identical.
So running this job on every startup plus every 24h, which resets
``updated_at`` each time it actually touches a row, does not over-decay or
under-decay relative to one long-elapsed-time pass; it converges to exactly
the same place. This also explains the D2 interaction with per-event decay:
if a user got a fresh alert (and therefore an ``updated_at`` bump) 3 hours
ago, days_elapsed for them right now is ~0.125, so this job barely touches
their score (0.98**0.125 ≈ 0.9975) — correct, since the per-event decay
already accounted for today's activity and this job isn't meant to
double-decay the same day's contribution twice.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.behavior_profile import BehaviorProfile

logger = logging.getLogger(__name__)


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalise to naive UTC.

    Same fix as profiler.py's ``_to_naive_utc`` (and detection/rules/
    port_scan.py's equivalent): SQLite strips tzinfo on round-trip even for
    ``DateTime(timezone=True)`` columns, so a value freshly computed with
    ``datetime.now(timezone.utc)`` (aware) can't be subtracted from a value
    re-read from the DB (naive, on SQLite; aware, on Postgres) without this
    normalisation — comparing aware and naive datetimes raises TypeError.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def run_decay_pass(db: Session, settings: Settings | None = None) -> dict:
    """Decay every eligible user's rolling risk score by elapsed wall-clock
    time since their profile was last touched.

    Queries ``BehaviorProfile`` rows with ``user_risk_score >
    settings.DECAY_SCORE_FLOOR`` (profiles at/below the floor are already
    effectively zero — skipped entirely, not even read into the update set).
    For each, computes the decayed score per the formula in this module's
    docstring, using ``profile.updated_at`` as the anchor (falling back to
    ``created_at`` for a profile that's never been updated since creation,
    since ``updated_at`` has no ``server_default`` and can be NULL until the
    first UPDATE — see models/behavior_profile.py). A result that drops
    below the floor is clamped to exactly 0.0 rather than left as an
    ever-shrinking non-zero remainder.

    Does NOT commit — the caller's responsibility, matching the pattern
    established by ``BehaviorProfiler``'s methods elsewhere in this codebase
    (they flush, they don't commit). Pure DB-session-in, dict-out: no
    scheduler or FastAPI app needs to be running to call this directly,
    which is what makes it independently testable.

    Returns a summary dict: ``profiles_processed`` (rows considered),
    ``profiles_decayed`` (rows whose score actually changed),
    ``total_score_removed`` (sum of before-minus-after across all processed
    rows).
    """
    s = settings or get_settings()
    now = _as_naive_utc(datetime.now(timezone.utc))

    profiles = (
        db.query(BehaviorProfile).filter(BehaviorProfile.user_risk_score > s.DECAY_SCORE_FLOOR).all()
    )

    profiles_processed = 0
    profiles_decayed = 0
    total_score_removed = 0.0

    for profile in profiles:
        profiles_processed += 1
        before = profile.user_risk_score

        anchor = profile.updated_at if profile.updated_at is not None else profile.created_at
        anchor = _as_naive_utc(anchor)
        # Defensive clamp: a future-dated anchor (clock skew, bad test data)
        # must never *increase* a score — rate < 1 raised to a negative
        # exponent would do exactly that, which is never correct for decay.
        days_elapsed = max(0.0, (now - anchor).total_seconds() / 86400.0)

        decayed_score = before * (s.DAILY_DECAY_RATE**days_elapsed)
        if decayed_score < s.DECAY_SCORE_FLOOR:
            decayed_score = 0.0

        if decayed_score != before:
            profile.user_risk_score = decayed_score
            db.add(profile)
            profiles_decayed += 1
            total_score_removed += before - decayed_score

    db.flush()

    logger.info(
        "Risk-decay pass: profiles_processed=%d profiles_decayed=%d total_score_removed=%.4f",
        profiles_processed,
        profiles_decayed,
        total_score_removed,
    )

    return {
        "profiles_processed": profiles_processed,
        "profiles_decayed": profiles_decayed,
        "total_score_removed": total_score_removed,
    }
