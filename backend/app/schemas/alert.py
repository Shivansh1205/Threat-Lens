"""Pydantic DTOs for alert responses (`GET /alerts`)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Severity


class AlertOut(BaseModel):
    """Alert as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    alert_type: str
    severity: Severity
    score: int
    raw_severity: Severity
    raw_score: int
    message: str
    triggered_by_event_id: UUID | None = None
    explanation: str | None = None
    mitigation_steps: list | dict | None = None
    resolved: bool
    resolved_at: datetime | None = None
    created_at: datetime
