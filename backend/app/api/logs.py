"""Single-event ingestion shared by scripts and the collector batch API."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.detection.registry import get_registry
from app.detection.settings import get_detection_thresholds
from app.models.log_event import LogEvent
from app.models.user import User
from app.profiling.profiler import BehaviorProfiler
from app.realtime.websocket_manager import get_ws_manager
from app.schemas.log_event import LogEventIn

router = APIRouter(tags=["ingestion"])
class LogIngestResult(BaseModel):
    event_id: UUID
    alert_ids: list[UUID]


def persist_event(payload: LogEventIn, db: Session) -> tuple[LogEvent, list]:
    """Persist and evaluate one validated event without committing it."""
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(User)
        .values(user_id=payload.user_id, first_seen_at=now, last_seen_at=now)
        .on_conflict_do_update(index_elements=["user_id"], set_={"last_seen_at": now})
    )
    db.execute(stmt)
    db.flush()

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
        source_id=payload.source_id,
        external_event_id=payload.external_event_id,
        http_method=payload.http_method,
        http_status=payload.http_status,
        response_time_ms=payload.response_time_ms,
        bytes_sent=payload.bytes_sent,
        host=payload.host,
        referrer=payload.referrer,
        event_metadata=payload.event_metadata,
        raw_json=payload.model_dump(mode="json"),
    )
    db.add(event)
    db.flush()

    thresholds = get_detection_thresholds()
    profiler = BehaviorProfiler(db, get_settings().EMA_ALPHA, thresholds=thresholds)
    profile = profiler.get_or_create(payload.user_id)
    profiler.compute_deviation(event, profile)
    alerts = get_registry().run_all(event, db, profile, thresholds)
    profiler.update(event)
    return event, alerts


def publish_alerts(alerts: list, background_tasks: BackgroundTasks) -> None:
    """Run best-effort post-commit delivery for newly-created alerts."""
    for alert in alerts:
        get_ws_manager().schedule_broadcast(
            {
                "id": str(alert.id),
                "user_id": alert.user_id,
                "alert_type": alert.alert_type,
                "severity": alert.severity.value,
                "score": alert.score,
                "message": alert.message,
                "evidence": alert.evidence,
                "created_at": (
                    alert.created_at.isoformat() if alert.created_at else None
                ),
            }
        )


@router.post(
    "/log", status_code=status.HTTP_201_CREATED, response_model=LogIngestResult
)
def ingest_log(
    payload: LogEventIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LogIngestResult:
    event, alerts = persist_event(payload, db)
    db.commit()
    publish_alerts(alerts, background_tasks)
    return LogIngestResult(event_id=event.id, alert_ids=[alert.id for alert in alerts])
