"""Pydantic DTOs for log ingestion (`POST /log`) and log responses."""

from datetime import datetime, timezone
from ipaddress import ip_address
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import EventType


class LogEventIn(BaseModel):
    """Incoming log event payload.

    Strict: unknown fields are rejected (``extra="forbid"``) and the core
    identifying fields are required. Optional network/context fields may be
    omitted.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=200)
    ip: str = Field(min_length=2, max_length=64)
    timestamp: datetime
    event_type: EventType
    status: str = Field(min_length=1, max_length=64)

    port: int | None = None
    endpoint: str | None = Field(default=None, max_length=2048)
    user_agent: str | None = Field(default=None, max_length=1024)
    country: str | None = Field(default=None, max_length=100)
    source_id: str | None = Field(default=None, max_length=100)
    external_event_id: str | None = Field(default=None, max_length=128)
    http_method: str | None = Field(default=None, max_length=16)
    http_status: int | None = Field(default=None, ge=100, le=599)
    response_time_ms: float | None = Field(default=None, ge=0)
    bytes_sent: int | None = Field(default=None, ge=0)
    host: str | None = Field(default=None, max_length=255)
    referrer: str | None = Field(default=None, max_length=2048)
    event_metadata: dict | None = None

    @field_validator("ip")
    @classmethod
    def _valid_ip(cls, value: str) -> str:
        return str(ip_address(value))

    @field_validator("timestamp")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("http_method")
    @classmethod
    def _normalize_method(cls, value: str | None) -> str | None:
        return value.upper() if value else None


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
    source_id: str | None = None
    external_event_id: str | None = None
    http_method: str | None = None
    http_status: int | None = None
    response_time_ms: float | None = None
    bytes_sent: int | None = None
    host: str | None = None
    referrer: str | None = None
    event_metadata: dict | None = None
    created_at: datetime
