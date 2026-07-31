"""Pydantic DTOs for log ingestion (`POST /log`) and log responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import EventType


class LogEventIn(BaseModel):
    """Incoming log event payload.

    Strict: unknown fields are rejected (``extra="forbid"``) and the core
    identifying fields are required. Optional network/context fields may be
    omitted.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    ip: str
    timestamp: datetime
    event_type: EventType
    status: str

    port: int | None = None
    endpoint: str | None = None
    user_agent: str | None = None
    country: str | None = None


class LogEventOut(BaseModel):
    """Log event as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    ip: str
    timestamp: datetime
    event_type: EventType
    status: str
    port: int | None = None
    endpoint: str | None = None
    user_agent: str | None = None
    country: str | None = None
    created_at: datetime
