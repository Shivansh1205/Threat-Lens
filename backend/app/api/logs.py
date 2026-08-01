"""Log ingestion endpoint: `POST /log`.

The synchronous ingest path — validate, upsert the user, persist the event,
run the detector registry, return what fired. A message queue between ingest
and detection is deliberately skipped (see PHASES.md open question for Phase
2): direct call is fine at our volumes.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai.explainability import generate_explanation_task
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.detection.registry import get_registry
from app.models.log_event import LogEvent
from app.models.user import User
from app.profiling.profiler import BehaviorProfiler
from app.schemas.log_event import LogEventIn

router = APIRouter(tags=["ingestion"])


class LogIngestResult(BaseModel):
    """Response for a successful ingest: the stored event id and any alerts."""

    event_id: UUID
    alert_ids: list[UUID]


@router.post("/log", status_code=status.HTTP_201_CREATED, response_model=LogIngestResult)
def ingest_log(
    payload: LogEventIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LogIngestResult:
    now = datetime.now(timezone.utc)

    # 1. Upsert the user — ON CONFLICT handles concurrent inserts safely.
    stmt = (
        pg_insert(User)
        .values(user_id=payload.user_id, first_seen_at=now, last_seen_at=now)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={"last_seen_at": now},
        )
    )
    db.execute(stmt)
    db.flush()

    # 2. Persist the event, keeping the raw payload verbatim for audit.
    event = LogEvent(
        user_id=payload.user_id,
        ip=payload.ip,
        timestamp=payload.timestamp,
        event_type=payload.event_type,
        status=payload.status,
        port=payload.port,
        endpoint=payload.endpoint,
        user_agent=payload.user_agent,
        country=payload.country,
        raw_json=payload.model_dump(mode="json"),
    )
    db.add(event)
    db.flush()

    # 3. Load the user's profile and compute THIS event's deviation score,
    # before running detection or applying this event's own mutations.
    #
    # Ordering here is deliberate and has two separate constraints that both
    # have to hold at once (Phase 5 note — see Phase 4's near-identical
    # ordering bug for why this needs spelling out rather than guessing):
    #
    #   (a) UnusualIpDetector reads BehaviorProfile.known_ips / login_count,
    #       and BehaviorProfiler.update() unconditionally folds this event's
    #       IP into known_ips. If detection ran after the profile's
    #       known_ips/login_count were mutated for this event, the detector
    #       would always find its own event's IP already "known" and could
    #       never fire (the Phase 4 bug). So detection must run against the
    #       profile in its PRE-mutation state.
    #
    #   (b) RiskScorer needs profile.deviation_score to reflect THIS event
    #       (how unusual *this* IP/hour/frequency was), not the previous
    #       event's leftover value. deviation_score is normally computed as
    #       the first step inside profiler.update(), which runs *after*
    #       detection per (a) — so if we waited for update() to compute it,
    #       RiskScorer would score every alert against stale, one-event-old
    #       context.
    #
    # Resolution: call BehaviorProfiler.compute_deviation() directly, ahead
    # of both detection and the rest of update(). It only ever *writes*
    # profile.deviation_score — it never touches known_ips / login_count /
    # the EMA fields — so calling it standalone here doesn't disturb the
    # pre-mutation state that (a) depends on. Detection and RiskScorer then
    # both see the profile mid-way through "this event's" processing: prior
    # known_ips/login_count (for the detector), current deviation_score (for
    # the scorer). profiler.update() below recomputes compute_deviation()
    # again as its own first step — same inputs, same result, so this is a
    # harmless redundant assignment, not a second source of truth — and then
    # applies the actual known_ips/EMA mutations for next time.
    profiler = BehaviorProfiler(db, get_settings().EMA_ALPHA)
    profile = profiler.get_or_create(payload.user_id)
    profiler.compute_deviation(event, profile)

    # 4. Run the real detectors + risk scoring against that pre-mutation,
    # current-deviation profile state.
    alerts = get_registry().run_all(event, db, profile)

    # 5. Now apply this event's own mutations to the persistent behavior
    # profile (known IPs, login-hour EMA, session duration) — safe to do only
    # now that both detection and scoring have already read the prior state
    # they each depend on.
    profiler.update(event)

    # Single commit: event, user upsert, alerts (with their risk-adjusted
    # scores), and the profile (deviation_score, user_risk_score, known_ips,
    # EMAs) all land together, even when no alerts fired.
    db.commit()

    # 6. Schedule explanation generation for each new alert — AFTER the
    # response would be considered complete, never inline. Alerts are
    # persisted above with explanation=NULL/mitigation_steps=NULL; a
    # BackgroundTasks job (Starlette's, no new dependency) calls the LLM and
    # updates the row once it's done, which can take several seconds. Doing
    # this synchronously here would make ingestion latency depend on
    # Ollama's response time — under concurrent load (e.g. the port_scan
    # scenario's 60 near-simultaneous events) that's exactly the kind of
    # coupling that caused the connection-pool exhaustion problems in
    # earlier phases, just worse. GET /api/v1/alerts legitimately returning
    # explanation=null for a very recent alert is expected, not a bug.
    #
    # A fresh session is created inside the task via SessionLocal (passed as
    # a factory, not an instance) rather than reusing `db` — this request's
    # session may already be closed by the time the background task runs.
    for alert in alerts:
        background_tasks.add_task(generate_explanation_task, alert.id, SessionLocal)

    return LogIngestResult(event_id=event.id, alert_ids=[a.id for a in alerts])
