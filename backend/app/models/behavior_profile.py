"""BehaviorProfile model — a persistent per-user behavioral baseline.

Unlike detector sliding windows (intentionally in-memory and ephemeral), this
is a DB row: known IPs, login-hour patterns, and session stats must survive a
uvicorn restart. All EMA math lives in `app.profiling.profiler.BehaviorProfiler`;
this module only defines storage.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# JSONB on Postgres, generic JSON on SQLite (so the test suite can run in-memory).
JSONVariant = JSONB().with_variant(JSON(), "sqlite")


class BehaviorProfile(Base):
    """Per-user behavioral baseline, updated on every ingested event.

    ``known_ips`` is a JSON list of strings rather than a relational table —
    simple, and small enough per-user that this isn't a real cost. EMA fields
    (``typical_login_hour``, ``login_hour_variance``,
    ``typical_days_between_logins``, ``avg_session_duration_seconds``) are
    intentionally two floats each rather than histograms — see ARCHITECTURE.md
    Phase 4 notes: a decaying scalar mean/variance is simpler to reason about
    and update than a 24-bin histogram, and decays naturally as behavior shifts.
    """

    __tablename__ = "behavior_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), unique=True, index=True, nullable=False
    )

    known_ips: Mapped[list] = mapped_column(JSONVariant, nullable=False, default=list)

    login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    typical_login_hour: Mapped[float | None] = mapped_column(Float, nullable=True)
    login_hour_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    typical_days_between_logins: Mapped[float | None] = mapped_column(Float, nullable=True)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_logout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    avg_session_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    deviation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Rolling, decaying cumulative risk for this user (Phase 5 / RiskScorer).
    # Distinct from deviation_score: deviation_score is "how odd was the most
    # recent event", user_risk_score is "how concerning is this user's
    # pattern over time, across every alert they've triggered." Indexed
    # because GET /api/v1/users/high-risk sorts on it. Decays once per new
    # alert event, not per elapsed time — see app/scoring/risk_scorer.py and
    # PHASES.md for why true time-based decay is a later-phase follow-up.
    user_risk_score: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, index=True
    )

    # Dedup key: skip processing if an incoming event's timestamp is <= this.
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
