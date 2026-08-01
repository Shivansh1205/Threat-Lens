"""Pydantic DTO for behavior profile responses.

Read by `GET /api/v1/users/{user_id}/profile` (see app/api/users.py).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BehaviorProfileOut(BaseModel):
    """A user's behavioral baseline, as returned by the API.

    ``days_since_first_seen`` is the one derived field this endpoint adds
    beyond the raw model columns — computed from ``created_at`` at request
    time, not stored. Deliberately not adding more than this: a historical
    time series of ``user_risk_score`` would be genuinely useful too, but
    the DB only ever stores the current value (no history table), so it
    isn't reconstructable — noted as a known limitation rather than faked.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    known_ips: list[str]
    login_count: int
    typical_login_hour: float | None = None
    login_hour_variance: float | None = None
    typical_days_between_logins: float | None = None
    last_login_at: datetime | None = None
    last_logout_at: datetime | None = None
    avg_session_duration_seconds: float | None = None
    total_sessions: int
    deviation_score: float
    user_risk_score: float
    last_event_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
    days_since_first_seen: float
