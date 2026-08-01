"""High-risk users endpoint: `GET /users/high-risk`.

Ranks users by their rolling ``BehaviorProfile.user_risk_score`` (see
app/scoring/risk_scorer.py) — the "flag users from entry patterns over time"
capability. Users who have never triggered an alert stay at user_risk_score
== 0.0 forever (correctly — they haven't earned a place on this list) and are
excluded here.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.behavior_profile import BehaviorProfile
from app.schemas.user_risk import HighRiskUserOut

router = APIRouter(tags=["users"])


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
