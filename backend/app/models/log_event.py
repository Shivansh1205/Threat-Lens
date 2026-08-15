"""LogEvent model — a single raw ingested event, persisted verbatim for audit."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.schemas.common import EventType

# JSONB on Postgres, generic JSON on SQLite (so the test suite can run in-memory).
JSONVariant = JSONB().with_variant(JSON(), "sqlite")


class LogEvent(Base):
    """A structured log event.

    ``raw_json`` keeps the original incoming payload untouched for audit and
    replay; the flattened columns are extracted for querying and detection.
    """

    __tablename__ = "log_events"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_event_id", name="uq_log_event_source_external"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), index=True, nullable=False
    )
    ip: Mapped[str] = mapped_column(String, index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="event_type"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)

    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        String(100), index=True, nullable=True
    )
    external_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    http_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    bytes_sent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    raw_json: Mapped[dict] = mapped_column(JSONVariant, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
