"""Pydantic DTO for the high-risk-users ranking (`GET /users/high-risk`)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HighRiskUserOut(BaseModel):
    """One row of the high-risk-users ranking."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    user_risk_score: float
    login_count: int
    known_ip_count: int
    last_event_at: datetime | None = None
