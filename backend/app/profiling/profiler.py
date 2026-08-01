"""BehaviorProfiler — builds and maintains each user's persistent baseline.

Unlike detector sliding windows, a ``BehaviorProfile`` is a DB row: known IPs,
login-hour EMA, session-duration EMA, and the rolling deviation score all
survive a uvicorn restart. This is what makes the system adaptive rather than
purely reactive — detectors answer "did this event match a fixed rule?"; the
profiler answers "does this look like this particular user?"

Design notes (see PHASES.md Phase 4 open questions / ARCHITECTURE.md):
- All EMA updates share one alpha (``settings.EMA_ALPHA``) — no per-metric
  tuning. Simpler to reason about, and this is a v1.
- Login-hour distribution is stored as two floats (EMA mean + EMA variance),
  not a 24-bin histogram. Cheaper to store, decays naturally, easy to reason
  about as a moving Gaussian-ish estimate.
- ``compute_deviation`` is evaluated against the profile's state *before* the
  current event's own login/logout mutations are applied — otherwise a brand
  new IP would already be in ``known_ips`` (added by this same event) by the
  time novelty is checked, and the score would always read 0. Anomaly
  detection compares an observation to the *prior* baseline, then updates the
  baseline; that ordering is preserved here even though it means
  `update()` calls `compute_deviation()` before mutating login/logout fields.

IMPORTANT — pipeline ordering with UnusualIpDetector: ``update()`` adds the
current event's IP to ``known_ips`` unconditionally (see ``_apply_login``).
That means whoever calls ``update()`` and then reads ``get_known_ips()``
afterward will always find the current event's own IP already present — never
useful for "is this IP new" checks. `api/logs.py` therefore runs detection
*before* calling `profiler.update()` for the same event, so
`UnusualIpDetector` observes `known_ips`/`login_count` as they stood prior to
this event (matching how the Phase 3 in-memory version did a single
check-then-add inside one method call). `is_past_bootstrap` uses `>=` rather
than the more obvious `>` specifically to compensate: read *before*
`update()` increments `login_count` for this event, the count still reflects
only prior logins, so the boundary needs `>=` to land on the same event (the
4th login, with `UNUSUAL_IP_BOOTSTRAP_COUNT=3`) that the original detector
treated as first-past-bootstrap.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent
from app.schemas.common import EventType

_LOGIN_TYPES = {EventType.LOGIN_SUCCESS, EventType.LOGIN_FAILURE}


def _to_naive_utc(ts: datetime) -> datetime:
    """Normalise to naive UTC so comparisons never mix aware/naive datetimes.

    SQLite strips tzinfo on round-trip; without this, comparing a freshly
    parsed (aware) event timestamp against a value re-read from the DB
    (naive) raises TypeError. Same fix applied in sliding_window.py and
    detection/rules/port_scan.py.
    """
    if ts.tzinfo is None:
        return ts
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


class BehaviorProfiler:
    """Reads and updates a user's persistent behavioral baseline."""

    def __init__(self, db: Session, alpha: float | None = None) -> None:
        self.db = db
        self.alpha = alpha if alpha is not None else get_settings().EMA_ALPHA
        self._settings = get_settings()

    # ------------------------------------------------------------ lookup

    def get_or_create(self, user_id: str) -> BehaviorProfile:
        """Return the user's profile, creating an empty one if needed.

        Uses an ``INSERT ... ON CONFLICT DO NOTHING`` + follow-up SELECT so a
        burst of concurrent first-events for a brand-new user can't race two
        inserts into a unique-constraint violation (same pattern as the User
        upsert in api/logs.py).
        """
        existing = (
            self.db.query(BehaviorProfile)
            .filter(BehaviorProfile.user_id == user_id)
            .one_or_none()
        )
        if existing is not None:
            return existing

        stmt = (
            pg_insert(BehaviorProfile)
            .values(user_id=user_id, known_ips=[])
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        self.db.execute(stmt)
        self.db.flush()

        return (
            self.db.query(BehaviorProfile)
            .filter(BehaviorProfile.user_id == user_id)
            .one()
        )

    def get_known_ips(self, user_id: str) -> set[str]:
        """Known-IP set for a user, read straight from the persisted profile."""
        profile = self.get_or_create(user_id)
        return set(profile.known_ips or [])

    def is_past_bootstrap(self, user_id: str) -> bool:
        """Whether this user has logged in enough times to trust known_ips.

        Uses `>=` rather than `>` — see the pipeline-ordering note in this
        module's docstring for why.
        """
        profile = self.get_or_create(user_id)
        return profile.login_count >= self._settings.UNUSUAL_IP_BOOTSTRAP_COUNT

    # ------------------------------------------------------------- update

    def update(self, event: LogEvent) -> BehaviorProfile:
        """Main entry point — called on every ingested event."""
        profile = self.get_or_create(event.user_id)
        ts = _to_naive_utc(event.timestamp)

        # Dedup: never let a replayed/duplicate event double-count.
        if profile.last_event_at is not None and ts <= _to_naive_utc(profile.last_event_at):
            return profile

        profile.last_event_at = event.timestamp

        # Deviation is scored against the PRIOR baseline, before this event's
        # own login/logout mutations touch known_ips / EMAs. See module docstring.
        self.compute_deviation(event, profile)

        if event.event_type in _LOGIN_TYPES:
            self._apply_login(profile, event, ts)
        elif event.event_type == EventType.LOGOUT:
            self._apply_logout(profile, event, ts)

        self.db.add(profile)
        self.db.flush()
        return profile

    def _apply_login(self, profile: BehaviorProfile, event: LogEvent, ts: datetime) -> None:
        profile.login_count += 1

        known = list(profile.known_ips or [])
        if event.ip not in known:
            known.append(event.ip)
            profile.known_ips = known

        hour = ts.hour + ts.minute / 60.0
        if profile.typical_login_hour is None:
            profile.typical_login_hour = hour
            profile.login_hour_variance = 0.0
        else:
            diff = hour - profile.typical_login_hour
            profile.typical_login_hour = (
                self.alpha * hour + (1 - self.alpha) * profile.typical_login_hour
            )
            prev_variance = profile.login_hour_variance or 0.0
            profile.login_hour_variance = self.alpha * (diff**2) + (1 - self.alpha) * prev_variance

        if profile.last_login_at is not None:
            days_gap = (ts - _to_naive_utc(profile.last_login_at)).total_seconds() / 86400.0
            if profile.typical_days_between_logins is None:
                profile.typical_days_between_logins = days_gap
            else:
                profile.typical_days_between_logins = (
                    self.alpha * days_gap
                    + (1 - self.alpha) * profile.typical_days_between_logins
                )

        profile.last_login_at = event.timestamp

    def _apply_logout(self, profile: BehaviorProfile, event: LogEvent, ts: datetime) -> None:
        if profile.last_login_at is not None:
            last_login_naive = _to_naive_utc(profile.last_login_at)
            last_logout_naive = (
                _to_naive_utc(profile.last_logout_at) if profile.last_logout_at else None
            )
            # Only count a session if this login hasn't already been paired
            # with a later logout (guards against duplicate/out-of-order LOGOUTs).
            if last_logout_naive is None or last_login_naive > last_logout_naive:
                duration = (ts - last_login_naive).total_seconds()
                if 0 < duration < 86400:  # sanity: ignore >24h "sessions"
                    if profile.avg_session_duration_seconds is None:
                        profile.avg_session_duration_seconds = duration
                    else:
                        profile.avg_session_duration_seconds = (
                            self.alpha * duration
                            + (1 - self.alpha) * profile.avg_session_duration_seconds
                        )
                    profile.total_sessions += 1

        profile.last_logout_at = event.timestamp

    # --------------------------------------------------------- deviation

    def compute_deviation(self, event: LogEvent, profile: BehaviorProfile) -> float:
        """Score 0.0-1.0: how anomalous is this event vs. the user's baseline.

        Computed and stored on ``profile.deviation_score`` here, but not used
        for alert generation yet — Phase 5's RiskScorer combines this with
        alert severity. Rule-based detectors remain the only alert source.
        """
        components: list[float] = []

        # -- IP novelty --
        # `>=` for consistency with is_past_bootstrap() — see module docstring.
        past_bootstrap = profile.login_count >= self._settings.UNUSUAL_IP_BOOTSTRAP_COUNT
        known = profile.known_ips or []
        ip_novelty = 1.0 if (past_bootstrap and event.ip not in known) else 0.0
        components.append(ip_novelty)

        # -- Hour-of-day deviation --
        hour_deviation = 0.0
        if profile.typical_login_hour is not None and (profile.login_hour_variance or 0.0) > 0:
            ts = _to_naive_utc(event.timestamp)
            hour = ts.hour + ts.minute / 60.0
            z = abs(hour - profile.typical_login_hour) / max(
                math.sqrt(profile.login_hour_variance), 0.5
            )
            hour_deviation = min(z / 3.0, 1.0)
        components.append(hour_deviation)

        # -- Login-frequency deviation --
        frequency_deviation = 0.0
        if profile.typical_days_between_logins is not None and profile.last_login_at is not None:
            ts = _to_naive_utc(event.timestamp)
            actual_gap = (ts - _to_naive_utc(profile.last_login_at)).total_seconds() / 86400.0
            expected_gap = profile.typical_days_between_logins
            if expected_gap > 0:
                ratio = actual_gap / expected_gap
                if ratio < 0.2:
                    frequency_deviation = min((0.2 - ratio) / 0.2, 1.0)
                elif ratio > 5.0:
                    frequency_deviation = min((ratio - 5.0) / 5.0, 1.0)
        components.append(frequency_deviation)

        nonzero = [c for c in components if c > 0.0]
        score = (sum(nonzero) / len(nonzero)) if nonzero else 0.0

        profile.deviation_score = score
        return score
