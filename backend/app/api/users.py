"""User endpoints: `GET /users/high-risk`, `GET /users/{user_id}/profile`.

The high-risk ranking sorts by rolling ``BehaviorProfile.user_risk_score``
(see app/scoring/risk_scorer.py) — the "flag users from entry patterns over
time" capability. Users who have never triggered an alert stay at
user_risk_score == 0.0 forever (correctly — they haven't earned a place on
that list) and are excluded there. The profile endpoint below has no such
exclusion — any user who has ever sent a login event has a profile, whether
or not they've ever been flagged.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.behavior_profile import BehaviorProfile
from app.schemas.behavior_profile import BehaviorProfileOut
from app.schemas.user_risk import HighRiskUserOut

router = APIRouter(tags=["users"])


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalise to naive UTC — same fix as profiler.py's ``_to_naive_utc``
    and decay_job.py's ``_as_naive_utc``: SQLite strips tzinfo on round-trip
    even for ``DateTime(timezone=True)`` columns, so a freshly computed
    aware "now" can't be subtracted from a value re-read from the DB
    without this normalisation.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/users/high-risk", response_model=list[HighRiskUserOut])
def high_risk_users(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[HighRiskUserOut]:
    """Users ranked by rolling risk score, descending. Excludes score == 0."""
    profiles = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.user_risk_score > 0)
        .order_by(BehaviorProfile.user_risk_score.desc())
        .limit(limit)
        .all()
    )

    return [
        HighRiskUserOut(
            user_id=p.user_id,
            user_risk_score=p.user_risk_score,
            login_count=p.login_count,
            known_ip_count=len(p.known_ips or []),
            last_event_at=p.last_event_at,
        )
        for p in profiles
    ]


@router.get("/users/{user_id}/profile", response_model=BehaviorProfileOut)
def get_user_profile(user_id: str, db: Session = Depends(get_db)) -> BehaviorProfileOut:
    """Full behavioral-profile detail for one user — the "inspect a single
    user's baseline" view (EMA fields, known IPs, deviation/risk scores).

    404 if the user has never sent a login event (no profile row exists —
    ``BehaviorProfiler.get_or_create`` is what would normally create one,
    and it's only ever called from the ingestion path, never from a read
    like this). Distinct from `GET /users/high-risk`, which only lists
    users with a nonzero rolling risk score — this endpoint has no such
    filter, since "inspect this user" is a valid ask even for someone who's
    never been flagged.
    """
    profile = db.query(BehaviorProfile).filter(BehaviorProfile.user_id == user_id).one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No behavioral profile for user_id={user_id!r}",
        )

    now = _as_naive_utc(datetime.now(timezone.utc))
    days_since_first_seen = (now - _as_naive_utc(profile.created_at)).total_seconds() / 86400.0

    return BehaviorProfileOut(
        id=profile.id,
        user_id=profile.user_id,
        known_ips=profile.known_ips or [],
        login_count=profile.login_count,
        typical_login_hour=profile.typical_login_hour,
        login_hour_variance=profile.login_hour_variance,
        typical_days_between_logins=profile.typical_days_between_logins,
        last_login_at=profile.last_login_at,
        last_logout_at=profile.last_logout_at,
        avg_session_duration_seconds=profile.avg_session_duration_seconds,
        total_sessions=profile.total_sessions,
        deviation_score=profile.deviation_score,
        user_risk_score=profile.user_risk_score,
        last_event_at=profile.last_event_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        days_since_first_seen=days_since_first_seen,
    )
