"""Log ingestion endpoint: `POST /log`.

The synchronous ingest path — validate, upsert the user, persist the event,
run the detector registry, return what fired. A message queue between ingest
and detection is deliberately skipped (see PHASES.md open question for Phase
2): direct call is fine at our volumes.

WHY THIS ENDPOINT STAYS `def`, NOT `async def` (Phase 7a note): adding the
WebSocket broadcast here raised the question of whether to convert
``ingest_log`` to ``async def`` so it could ``await
get_ws_manager().broadcast(...)`` directly. Decided against it, deliberately:

- FastAPI runs sync ``def`` endpoints on Starlette's threadpool — real OS
  threads, genuinely concurrent. That's the whole reason Phase 4 needed a
  ``threading.Lock`` in ``BruteForceDetector``/``PortScanDetector`` in the
  first place (two threads racing the same in-memory state). If this
  endpoint became ``async def``, FastAPI would instead run it directly on
  the single main event loop — and since every DB call here
  (``db.execute``/``db.flush``/``db.commit``, the whole detection/scoring/
  profiler pipeline) is *synchronous* SQLAlchemy, none of it is ever
  ``await``-ed, so nothing would yield back to the loop mid-request. In
  practice that means requests would stop being genuinely concurrent at
  all — each one would run to completion on the one loop thread before the
  next could even start, which is a straight throughput regression for
  bursty ingestion (e.g. generate_logs.py's 60-event port_scan burst)
  compared to today's real thread-level parallelism. It would also make the
  Phase 4 locks moot (no more thread interleaving to protect against) but
  for the wrong reason — accidentally serializing everything, not fixing
  anything.
- So the endpoint stays sync, and the broadcast is dispatched via
  ``WebSocketManager.schedule_broadcast()`` — a sync method that hands the
  actual ``async def broadcast()`` call to the main event loop via
  ``asyncio.run_coroutine_threadsafe`` (captured once at app startup, see
  main.py's lifespan handler). This is the standard, correct bridge for
  "call async code, from a different thread, targeting a specific already-
  running loop" — unlike ``asyncio.run()``, which would spin up a brand-new
  throwaway loop inside this worker thread and try to drive the live
  WebSocket objects (bound to the MAIN loop) from that foreign loop, which
  asyncio does not support safely. See
  app/realtime/websocket_manager.py's ``schedule_broadcast`` docstring for
  the full detail.
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
from app.realtime.websocket_manager import get_ws_manager
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

    # 6. Broadcast each new alert to connected dashboard clients — AFTER the
    # commit above, never before, so we never push something that could
    # still roll back. Payload is deliberately small/clean: id, user_id,
    # alert_type, severity, score, message, created_at. explanation/
    # mitigation_steps are NOT included — they don't exist yet at this point
    # (generated moments later by the background task below) and the
    # frontend can re-fetch full alert details on demand. Whether a second
    # "alert updated" push should fire once the explanation lands is left
    # for Prompt 7b to decide — not needed for the initial live-feed feature.
    for alert in alerts:
        get_ws_manager().schedule_broadcast(
            {
                "id": str(alert.id),
                "user_id": alert.user_id,
                "alert_type": alert.alert_type,
                "severity": alert.severity.value,
                "score": alert.score,
                "message": alert.message,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
        )

    # 7. Schedule explanation generation for each new alert — AFTER the
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
