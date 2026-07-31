"""Shared LogEvent builder for detector tests."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.models.log_event import LogEvent
from app.schemas.common import EventType


def make_event(
    user_id: str,
    event_type: EventType,
    timestamp: datetime,
    ip: str = "10.0.0.1",
    port: int | None = None,
    status: str = "ok",
) -> LogEvent:
    """Build an unpersisted LogEvent instance for detector unit tests."""
    return LogEvent(
        id=uuid4(),
        user_id=user_id,
        ip=ip,
        timestamp=timestamp,
        event_type=event_type,
        status=status,
        port=port,
        raw_json={},
        created_at=timestamp,
    )
