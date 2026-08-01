"""Pydantic DTO for behavior profile responses.

No endpoint reads this yet — Phase 5 adds `GET /profiles/{user_id}` (or
similar). Defined now so the model-to-schema mapping is exercised by tests
ahead of the API landing.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BehaviorProfileOut(BaseModel):
    """A user's behavioral baseline, as it will be returned by the API."""

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
    last_event_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
