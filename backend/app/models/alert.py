"""Alert model — a detection output linked to the event that triggered it."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.schemas.common import Severity

# JSONB on Postgres, generic JSON on SQLite (so the test suite can run in-memory).
JSONVariant = JSONB().with_variant(JSON(), "sqlite")


class Alert(Base):
    """A raised alert.

    ``explanation`` and ``mitigation_steps`` are populated later by the AI layer
    (Phase 6); they are nullable here so detection can emit an alert without
    waiting on the LLM.

    ``score``/``severity`` are the FINAL, risk-adjusted values — what the
    analyst sees and what the dashboard sorts/filters by. ``raw_score``/
    ``raw_severity`` preserve exactly what the detector originally assigned,
    before ``RiskScorer`` folded in the user's behavioral deviation_score
    (see app/scoring/risk_scorer.py). Keeping both is what makes the
    context-aware adjustment auditable: you can always see what the rule
    said vs. what the system concluded once behavioral context was applied.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), index=True, nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity, name="severity"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_severity: Mapped[Severity] = mapped_column(
        SAEnum(Severity, name="severity"), nullable=False
    )
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    triggered_by_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("log_events.id"), nullable=True
    )

    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitigation_steps: Mapped[dict | list | None] = mapped_column(JSONVariant, nullable=True)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
